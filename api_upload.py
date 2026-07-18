import uuid
import os
import traceback
import json
from fastapi import APIRouter, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from pathlib import Path
from minio_client import get_minio
from db import get_conn
from chunking import split_document
from embedding import get_embedding
from milvus_client import get_collection
from es_client import get_es
# 注释导入，不再调用llm
# from llm_client import call_llm
from config import settings, logger
from sqlalchemy import text

router = APIRouter(tags=["文件上传"])
TEMP_DIR = Path("temp_uploads")
TEMP_DIR.mkdir(exist_ok=True)

@router.post("/upload")
async def upload_files(files: list[UploadFile] = File(...), strategy: str = Form("markdown")):
    try:
        if not settings.is_flash_enabled():
            raise Exception("未配置工具模型密钥，无法执行文件预处理，请先补全配置。")
        doc_ids = []
        client = get_minio()
        bucket = settings.get_env("MINIO_BUCKET", "rag-files")
        col = get_collection()
        es = get_es()

        with get_conn() as db_conn:
            for f in files:
                doc_id = str(uuid.uuid4())
                doc_ids.append(doc_id)
                temp_path = TEMP_DIR / f.filename
                content = await f.read()

                with open(temp_path, "wb") as out:
                    out.write(content)
                client.fput_object(bucket, f"{doc_id}_{f.filename}", str(temp_path))

                # 插入任务记录
                insert_task = text("INSERT INTO upload_tasks (id, filename, status) VALUES (:id, :fn, :st)")
                db_conn.execute(insert_task, {"id": doc_id, "fn": f.filename, "st": "processing"})
                db_conn.commit()

                # 重命名变量：raw_text 替代 text，避免覆盖导入
                raw_text = content.decode("utf-8", errors="ignore")
                chunks = split_document(raw_text, strategy)
                if not chunks:
                    update_task = text("UPDATE upload_tasks SET status=:st WHERE id=:did")
                    db_conn.execute(update_task, {"st": "no_chunks", "did": doc_id})
                    db_conn.commit()
                    continue

                for idx, chunk in enumerate(chunks):
                    chunk_id = f"{doc_id}_{idx}"
                    # 固定默认标签，完全移除LLM调用逻辑
                    tags = {"tech": "未知", "level": "简单", "type": "概念"}
                    """
                    # 注释全部LLM生成代码，屏蔽报错源
                    try:
                        prompt = f"为以下文本生成JSON标签(包含:技术栈tech,难度level,题型type): {chunk[:200]}"
                        tags_str, _, _, _ = await call_llm(prompt, use_flash=True)
                        clean_str = tags_str.replace("```json", "").replace("```", "").strip()
                        tags = json.loads(clean_str)
                    except Exception as e:
                        logger.warning(f"分片{chunk_id}标签生成失败，使用默认标签: {e}")
                    """

                    emb = []
                    try:
                        emb = await get_embedding(chunk)
                        if len(emb) != 768:
                            raise Exception(f"向量维度错误，预期768，实际{len(emb)}")
                    except Exception as e:
                        logger.error(f"分片{chunk_id}向量化失败: {e}")
                        raise Exception(f"文档向量化失败：{str(e)}")

                    try:
                        data = [[chunk_id], [doc_id], [chunk], [tags], [emb]]
                        col.insert(data)
                    except Exception as e:
                        logger.error(f"Milvus插入分片{chunk_id}失败: {e}")
                        raise Exception(f"向量库写入失败：{str(e)}")

                    if es:
                        try:
                            es.index(
                                index="interview_docs",
                                id=chunk_id,
                                body={
                                    "doc_id": doc_id,
                                    "chunk_id": chunk_id,
                                    "content": chunk,
                                    "tags": [tags.get("tech", "")]
                                }
                            )
                        except Exception as e:
                            logger.warning(f"ES写入分片{chunk_id}失败: {e}")

                    # 插入分片元数据
                    insert_chunk = text("""
                        INSERT INTO chunk_meta (doc_id, chunk_id, content, tags)
                        VALUES (:did, :cid, :cont, :tg)
                    """)
                    db_conn.execute(insert_chunk, {
                        "did": doc_id,
                        "cid": chunk_id,
                        "cont": chunk,
                        "tg": json.dumps(tags)
                    })
                    db_conn.commit()

                # 更新完成状态
                update_finish = text("UPDATE upload_tasks SET status=:st WHERE id=:did")
                db_conn.execute(update_finish, {"st": "completed", "did": doc_id})
                db_conn.commit()

                if temp_path.exists():
                    os.remove(temp_path)

        return {"msg": "上传及向量化完成", "doc_ids": doc_ids}

    except Exception as e:
        err_stack = traceback.format_exc()
        logger.exception(f"文件上传接口崩溃：{e}\n完整堆栈：{err_stack}")
        raise Exception(str(e))

@router.websocket("/ws/upload")
async def ws_upload(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(json.dumps({"progress": 100, "status": "ready"}))
    except WebSocketDisconnect:
        pass

# 补全文档列表接口
@router.get("/documents")
async def list_documents():
    doc_list = []
    with get_conn() as conn:
        # 查询所有文档
        res = conn.execute(text("SELECT id, filename, status, created_at FROM upload_tasks ORDER BY created_at DESC"))
        rows = res.fetchall()
        for row in rows:
            doc_id, filename, status, create_time = row
            # 统计分片数量
            count_res = conn.execute(text("SELECT COUNT(*) FROM chunk_meta WHERE doc_id=:did"), {"did": doc_id})
            chunk_count = count_res.scalar()
            doc_list.append({
                "id": doc_id,
                "filename": filename,
                "status": status,
                "chunks": chunk_count,
                "created_at": str(create_time)
            })
    return {"data": doc_list}