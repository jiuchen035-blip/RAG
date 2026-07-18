from fastapi import APIRouter, Response, Query, HTTPException
from pydantic import BaseModel
from db import get_conn
from sqlalchemy import text
from milvus_client import get_collection
from es_client import get_es
from llm_client import call_llm
from embedding import get_embedding
from config import settings, logger
from typing import List
import io
import csv

router = APIRouter(tags=["面试问答"])


# ========== 修改1：QAReq 增加 enable_cot 开关参数 ==========
class QAReq(BaseModel):
    question: str
    model_type: str = "auto"
    enable_cot: bool = True  # COT思维链开关，默认开启


class BatchIdsRequest(BaseModel):
    ids: List[int]


class BatchExportRequest(BaseModel):
    ids: List[int]
    export_type: str = "md"


@router.post("/qa")
async def ask_question(req: QAReq):
    cache_enabled = settings.get_env("RAG_CACHE_ENABLED", "true") == "true"
    cached_data = None

    # 1. 查询缓存
    if cache_enabled:
        with get_conn() as conn:
            sql = text(
                "SELECT answer, model, tokens_in, tokens_out, cost FROM qa_history WHERE question=:q ORDER BY id DESC LIMIT 1")
            result = conn.execute(sql, {"q": req.question})
            cached = result.fetchone()
            if cached:
                return {
                    "answer": cached[0],
                    "cot": "",
                    "model": cached[1],
                    "tokens_in": cached[2],
                    "tokens_out": cached[3],
                    "cost": cached[4],
                    "cached": True
                }

    top_k = int(settings.get_env("RAG_TOP_K", "5"))
    es = get_es()
    context = ""

    if es:
        try:
            res = es.search(index="interview_docs", body={
                "query": {"match": {"content": req.question}},
                "size": top_k
            })
            hits = [h["_source"]["content"] for h in res["hits"]["hits"]]
            context = "\n".join(hits)[:1500]  # 截断上下文提速
        except Exception:
            pass

    if not context:
        try:
            emb = await get_embedding(req.question)
            col = get_collection()
            col.load()
            res = col.search([emb], "embedding", limit=top_k, output_fields=["content"])
            if res and res[0]:
                context = "\n".join([hit.entity.get("content") for hit in res[0]])[:1500]
        except Exception:
            pass

    use_flash = True
    if req.model_type == "pro":
        use_flash = False
    elif req.model_type == "auto":
        if len(req.question) > 50 or "代码" in req.question or "算法" in req.question:
            use_flash = False

    # ========== 修改2：根据 enable_cot 切换两套提示词 ==========
    if req.enable_cot:
        prompt = f"""
你是专业面试面试官，回答面试问题必须分两段输出：
第一段开头标记【思考过程】，分步拆解问题、梳理知识点、推理分析；
第二段开头标记【最终回答】，简洁给出标准答案。
参考上下文：
{context}
面试问题：{req.question}
"""
    else:
        # 关闭COT，极简提示词，只输出答案，速度大幅提升
        prompt = f"""
基于参考内容简洁回答面试问题，不要多余推理、不要分段标记，直接给出标准答案。
参考上下文：
{context}
面试问题：{req.question}
"""

    try:
        full_output, t_in, t_out, cost = await call_llm(prompt, use_flash=use_flash)
        # ========== 修改3：仅开启COT时才拆分思维链 ==========
        if req.enable_cot and "【思考过程】" in full_output and "【最终回答】" in full_output:
            cot_text = full_output.split("【最终回答】")[0].replace("【思考过程】", "").strip()
            final_answer = full_output.split("【最终回答】")[1].strip()
        else:
            # 关闭COT 或模型未分段，cot置空
            cot_text = ""
            final_answer = full_output
    except Exception as e:
        if not settings.is_flash_enabled() and use_flash:
            raise Exception("工具模型未启用，简单问题也无法回答，请在配置页面补全密钥。")
        raise e

    # 2. 插入问答历史（仅保存最终答案，cot不入库）
    with get_conn() as conn:
        insert_sql = text("""
                          INSERT INTO qa_history (question, answer, model, tokens_in, tokens_out, cost)
                          VALUES (:q, :ans, :m, :tin, :tout, :c)
                          """)
        conn.execute(insert_sql, {
            "q": req.question,
            "ans": final_answer,
            "m": "flash" if use_flash else "pro",
            "tin": t_in,
            "tout": t_out,
            "c": cost
        })
        conn.commit()

    return {
        "answer": final_answer,
        "cot": cot_text,
        "model": "flash" if use_flash else "pro",
        "tokens_in": t_in,
        "tokens_out": t_out,
        "cost": cost,
        "cached": False
    }


@router.get("/qa/history")
async def qa_history(page: int = 1, size: int = 20):
    with get_conn() as conn:
        sql = text("""
                   SELECT id, question, answer, model, cost, created_at
                   FROM qa_history
                   ORDER BY id DESC LIMIT :sz
                   OFFSET :off
                   """)
        result = conn.execute(sql, {"sz": size, "off": (page - 1) * size})
        rows = result.fetchall()
    return {
        "data": [
            {
                "id": r[0],
                "question": r[1],
                "answer": r[2],
                "model": r[3],
                "cost": r[4],
                "created_at": str(r[5])
            }
            for r in rows
        ]
    }


@router.delete("/qa/history/all")
async def clear_all_qa():
    try:
        with get_conn() as conn:
            clear_sql = text("DELETE FROM qa_history;")
            conn.execute(clear_sql)
            conn.commit()
        return {"success": True, "msg": "已清空全部问答历史记录"}
    except Exception as e:
        logger.error(f"清空问答历史异常: {str(e)}")
        raise Exception(f"清空数据库记录失败：{str(e)}")


@router.delete("/qa/history/{record_id}")
async def delete_single_qa(record_id: int):
    try:
        with get_conn() as conn:
            del_sql = text("DELETE FROM qa_history WHERE id = :rid")
            execute_result = conn.execute(del_sql, {"rid": record_id})
            conn.commit()
        if execute_result.rowcount <= 0:
            return {"success": False, "msg": "未找到该条历史记录"}
        return {"success": True, "msg": "删除单条问答历史成功"}
    except Exception as e:
        logger.error(f"删除单条问答记录异常: {str(e)}")
        raise Exception(f"删除失败：{str(e)}")


# ---------- 新增：批量删除 ----------
# ---------- 新增：批量删除 ----------
# 批量删除（改用POST，解决DELETE body 422报错）
@router.post("/qa/history/batch_delete")
async def delete_qa_batch(req: BatchIdsRequest):
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    logger.info(f"批量删除问答记录，ids={req.ids}")
    with get_conn() as conn:
        placeholders = ",".join([str(i) for i in req.ids])
        sql = text(f"DELETE FROM qa_history WHERE id IN ({placeholders})")
        result = conn.execute(sql)
        conn.commit()
    logger.info(f"成功删除 {result.rowcount} 条记录")
    return {"success": True, "msg": f"成功删除 {result.rowcount} 条记录"}


# ---------- 新增：批量导出选中 ----------
@router.post("/qa/history/export_batch")
async def export_qa_batch(req: BatchExportRequest):
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 不能为空")
    with get_conn() as conn:
        placeholders = ",".join([str(i) for i in req.ids])
        sql = text(f"""
            SELECT id, question, answer, model, tokens_in, tokens_out, cost, created_at
            FROM qa_history WHERE id IN ({placeholders}) ORDER BY id DESC
        """)
        rows = conn.execute(sql).fetchall()
    data_list = [
        {
            "id": r[0],
            "question": r[1],
            "answer": r[2],
            "model": r[3],
            "tokens_in": r[4],
            "tokens_out": r[5],
            "cost": float(r[6]),
            "created_at": str(r[7])
        }
        for r in rows
    ]

    if req.export_type == "md":
        md = "# 选中的面试问答记录\n\n"
        for item in data_list:
            md += f"""
## 记录 #{item['id']}
- 提问时间：{item['created_at']}
- 使用模型：{item['model']}
- 输入Token：{item['tokens_in']} | 输出Token：{item['tokens_out']}
- 费用：${item['cost']:.5f}

### 问题
{item['question']}

### 回答
{item['answer']}

---
"""
        buffer = io.StringIO(md)
        return Response(
            content=buffer.getvalue().encode("utf-8"),
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="qa_export_selected.md"'}
        )
    elif req.export_type == "excel":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["id", "question", "answer", "model", "tokens_in", "tokens_out", "cost", "created_at"]
        )
        writer.writeheader()
        writer.writerows(data_list)
        return Response(
            content=output.getvalue().encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="qa_export_selected.csv"'}
        )
    else:
        raise HTTPException(status_code=400, detail="导出类型仅支持 md / excel")


# ---------- 以下为原有的详情和导出全部接口 ----------
@router.get("/qa/history/detail/{record_id}")
async def get_qa_detail(record_id: int):
    with get_conn() as conn:
        sql = text("""
            SELECT id, question, answer, model, tokens_in, tokens_out, cost, created_at
            FROM qa_history WHERE id = :rid
        """)
        row = conn.execute(sql, {"rid": record_id}).fetchone()
    if not row:
        return {"success": False, "msg": "记录不存在"}
    return {
        "success": True,
        "data": {
            "id": row[0],
            "question": row[1],
            "answer": row[2],
            "model": row[3],
            "tokens_in": row[4],
            "tokens_out": row[5],
            "cost": float(row[6]),
            "created_at": str(row[7])
        }
    }


@router.get("/qa/history/export")
async def export_qa_history(export_type: str = Query("md", description="md / excel")):
    with get_conn() as conn:
        rows = conn.execute(text("""
            SELECT id, question, answer, model, tokens_in, tokens_out, cost, created_at
            FROM qa_history ORDER BY id DESC
        """)).fetchall()
    data_list = [
        {
            "id": r[0],
            "question": r[1],
            "answer": r[2],
            "model": r[3],
            "tokens_in": r[4],
            "tokens_out": r[5],
            "cost": float(r[6]),
            "created_at": str(r[7])
        }
        for r in rows
    ]

    if export_type == "md":
        md_content = "# 面试问答历史记录\n\n"
        for item in data_list:
            md_content += f"""
## 记录 #{item['id']}
- 提问时间：{item['created_at']}
- 使用模型：{item['model']}
- 输入Token：{item['tokens_in']} | 输出Token：{item['tokens_out']}
- 费用：${item['cost']:.5f}

### 问题
{item['question']}

### 回答
{item['answer']}

---
"""
        buffer = io.StringIO(md_content)
        return Response(
            content=buffer.getvalue().encode("utf-8"),
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="qa_history.md"'}
        )
    elif export_type == "excel":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["id", "question", "answer", "model", "tokens_in", "tokens_out", "cost", "created_at"]
        )
        writer.writeheader()
        writer.writerows(data_list)
        return Response(
            content=output.getvalue().encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="qa_history.csv"'}
        )
    else:
        raise HTTPException(status_code=400, detail="导出类型仅支持 md / excel")
