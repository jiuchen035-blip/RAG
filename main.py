import os
import sys
import traceback
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from config import settings, logger

app = FastAPI(title="Interview RAG Knowledge Base v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path("logs").mkdir(exist_ok=True)
Path("temp_uploads").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 改造全局异常中间件：打印完整堆栈，开发环境返回详情
@app.middleware("http")
async def global_exception_handler(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        err_stack = traceback.format_exc()
        logger.exception(f"未捕获异常: {e}\n完整堆栈：{err_stack}")
        msg = "服务器内部异常，请稍后重试"
        if "milvus" in str(e).lower():
            msg = "向量库连接异常，请检查Milvus容器状态"
        elif "psycopg" in str(e).lower() or "pg" in str(e).lower():
            msg = "数据库连接断开，请检查PostgreSQL服务"
        elif "minio" in str(e).lower():
            msg = "对象存储异常，请检查MinIO配置"
        elif "list index out of range" in str(e).lower():
            msg = "数据处理异常：未找到有效分片或内容，请检查文档质量"
        elif "api" in str(e).lower() or "openai" in str(e).lower() or "embedding" in str(e).lower():
            msg = "向量/大模型API调用失败，请检查密钥配置、模型文件或账户余额"
        # 开发环境返回完整报错，定位上传问题；上线后删除detail字段
        return JSONResponse(
            status_code=500,
            content={
                "error": msg,
                "detail": str(e),
                "stack": err_stack
            }
        )

@app.on_event("startup")
async def startup_event():
    logger.info("开始系统启动自检...")
    from db import init_pg
    from minio_client import init_minio
    from milvus_client import init_milvus
    from es_client import init_es

    if not init_pg():
        logger.error("[-] PostgreSQL 初始化失败，请确认 docker-compose up -d 已执行且 5432 端口正常。服务阻断。")
        sys.exit(1)
    logger.info("[+] PostgreSQL 连通并初始化成功")

    if not init_minio():
        logger.error("[-] MinIO 初始化失败，请确认 9000 端口正常及账号密码正确。服务阻断。")
        sys.exit(1)
    logger.info("[+] MinIO 连通并初始化成功")

    if not init_milvus():
        logger.error("[-] Milvus 初始化失败，请确认 19530 端口正常及 etcd 状态。服务阻断。")
        sys.exit(1)
    logger.info("[+] Milvus 连通并初始化成功")

    if not init_es():
        logger.warning("[!] Elasticsearch 初始化失败，检索将降级为仅向量召回。")
    else:
        logger.info("[+] Elasticsearch 连通并初始化成功")

    logger.info("系统启动自检完成，服务就绪。")

from api_config import router as config_router
from api_upload import router as upload_router
from api_chunks import router as chunks_router
from api_ops import router as ops_router
from api_qa import router as qa_router

app.include_router(config_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(chunks_router, prefix="/api")
app.include_router(ops_router, prefix="/api")
app.include_router(qa_router, prefix="/api")

@app.get("/")
async def root():
    return FileResponse("static/index.html")