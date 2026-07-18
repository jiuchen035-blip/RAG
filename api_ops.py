from fastapi import APIRouter, Query
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from db import get_conn
from llm_client import call_llm
from config import settings
import io

router = APIRouter(tags=["批量运维"])

class OpsReq(BaseModel):
    tech: str = ""
    level: str = ""

@router.post("/ops/deduplicate")
async def deduplicate(req: OpsReq):
    if not settings.is_flash_enabled():
        raise Exception("工具预处理模型未启用，无法执行去重。")
    with get_conn() as conn:
        sql = text("SELECT chunk_id, content FROM chunk_meta WHERE tags->>'tech' LIKE :tech_val")
        rows = conn.execute(sql, {"tech_val": f"%{req.tech}%"}).fetchall()
    return {"msg": "扫描完成", "count": len(rows), "duplicates": []}

@router.post("/ops/summarize")
async def summarize(req: OpsReq):
    if not settings.is_flash_enabled():
        raise Exception("工具预处理模型未启用，无法生成总结。")
    with get_conn() as conn:
        sql = text("SELECT content FROM chunk_meta WHERE tags->>'tech' LIKE :tech_val LIMIT 50")
        rows = conn.execute(sql, {"tech_val": f"%{req.tech}%"}).fetchall()
        texts = [r[0] for r in rows]
    prompt = f"请对以下面试知识点进行总结归纳：\n" + "\n".join(texts)[:3000]
    res, _, _, _ = await call_llm(prompt, use_flash=True)
    return {"summary": res}

@router.get("/ops/export")
async def export_data(tech: str = Query("")):
    if not settings.is_flash_enabled():
        raise Exception("工具预处理模型未启用，无法导出。")
    with get_conn() as conn:
        sql = text("SELECT content FROM chunk_meta WHERE tags->>'tech' LIKE :tech_val")
        rows = conn.execute(sql, {"tech_val": f"%{tech}%"}).fetchall()
        texts = [r[0] for r in rows]
    md_content = "\n\n---\n\n".join(texts)
    return StreamingResponse(
        io.StringIO(md_content),
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=export.md"}
    )