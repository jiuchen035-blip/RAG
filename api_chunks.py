from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from milvus_client import get_collection, rebuild_collection
from pymilvus import MilvusException
from db import get_conn
from minio_client import get_minio
from es_client import get_es
from config import settings

router = APIRouter(tags=["分片管理"])

@router.get("/chunks/{doc_id}")
async def get_chunks(doc_id: str, page: int = 1, size: int = 20):
    with get_conn() as conn:
        # 查询分片数据
        sql_data = text("""
            SELECT id, chunk_id, content, tags 
            FROM chunk_meta 
            WHERE doc_id = :docid 
            ORDER BY id LIMIT :sz OFFSET :off
        """)
        rows = conn.execute(
            sql_data,
            {"docid": doc_id, "sz": size, "off": (page - 1) * size}
        ).fetchall()

        # 查询总数
        sql_count = text("SELECT count(*) FROM chunk_meta WHERE doc_id = :docid")
        total = conn.execute(sql_count, {"docid": doc_id}).fetchone()[0]

    return {
        "data": [
            {"id": r[0], "chunk_id": r[1], "content": r[2], "tags": r[3]}
            for r in rows
        ],
        "total": total
    }

class ChunkUpdateReq(BaseModel):
    chunk_id: str
    content: str

@router.put("/chunks/edit")
async def edit_chunk(req: ChunkUpdateReq):
    with get_conn() as conn:
        sql = text("UPDATE chunk_meta SET content = :cnt WHERE chunk_id = :cid")
        conn.execute(sql, {"cnt": req.content, "cid": req.chunk_id})
        conn.commit()
    return {"msg": "更新成功"}

class ChunkMergeReq(BaseModel):
    chunk_ids: list[str]
    doc_id: str

@router.post("/chunks/merge")
async def merge_chunks(req: ChunkMergeReq):
    merged = ""
    new_id = f"{req.doc_id}_merged_{req.chunk_ids[0]}"

    with get_conn() as conn:
        # 读取待合并内容
        sql_read = text("SELECT content FROM chunk_meta WHERE chunk_id = ANY(:cid_list)")
        texts = [r[0] for r in conn.execute(sql_read, {"cid_list": req.chunk_ids}).fetchall()]
        merged = "\n".join(texts)

        # 删除旧分片
        sql_del = text("DELETE FROM chunk_meta WHERE chunk_id = ANY(:cid_list)")
        conn.execute(sql_del, {"cid_list": req.chunk_ids})

        # 插入合并后的分片
        sql_insert = text("""
            INSERT INTO chunk_meta (doc_id, chunk_id, content, tags) 
            VALUES (:did, :newcid, :content, :tag)
        """)
        conn.execute(
            sql_insert,
            {
                "did": req.doc_id,
                "newcid": new_id,
                "content": merged,
                "tag": "{}"
            }
        )
        conn.commit()
    return {"msg": "合并成功", "new_chunk_id": new_id}

@router.delete("/chunks/{chunk_id}")
async def delete_chunk(chunk_id: str):
    with get_conn() as conn:
        sql = text("DELETE FROM chunk_meta WHERE chunk_id = :cid")
        conn.execute(sql, {"cid": chunk_id})
        conn.commit()
    # Milvus 删除逻辑
    try:
        col = get_collection()
        col.delete(f"id in ['{chunk_id}']")
    except MilvusException:
        pass
    return {"msg": "删除成功"}

@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    cids = []
    file_name = None
    with get_conn() as conn:
        # 获取所有分片ID
        sql_get_cid = text("SELECT chunk_id FROM chunk_meta WHERE doc_id = :did")
        cids = [r[0] for r in conn.execute(sql_get_cid, {"did": doc_id}).fetchall()]

        # 删除分片记录
        sql_del_chunk = text("DELETE FROM chunk_meta WHERE doc_id = :did")
        conn.execute(sql_del_chunk, {"did": doc_id})

        # 查询上传文件名称
        sql_get_file = text("SELECT filename FROM upload_tasks WHERE id = :did")
        row = conn.execute(sql_get_file, {"did": doc_id}).fetchone()
        if row:
            file_name = row[0]

        # 删除上传任务记录
        sql_del_upload = text("DELETE FROM upload_tasks WHERE id = :did")
        conn.execute(sql_del_upload, {"did": doc_id})

        conn.commit()

    # Milvus 删除向量
    try:
        col = get_collection()
        if cids:
            col.delete(f"id in {cids}")
    except MilvusException:
        pass

    # MinIO 删除文件
    if file_name:
        try:
            client = get_minio()
            bucket = settings.get_env("MINIO_BUCKET", "rag-files")
            client.remove_object(bucket, f"{doc_id}_{file_name}")
        except Exception:
            pass

    # ES 删除文档
    es = get_es()
    if es:
        for cid in cids:
            try:
                es.delete(index="interview_docs", id=cid)
            except Exception:
                pass
    return {"msg": "文档已全量删除"}

@router.post("/milvus/rebuild")
async def rebuild_milvus():
    if not rebuild_collection():
        raise Exception("重建向量集合失败，请检查Milvus容器状态")
    return {"msg": "重建成功"}