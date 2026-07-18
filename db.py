from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv
from pathlib import Path
import os
from contextlib import contextmanager

# 加载环境配置
load_dotenv(Path(__file__).parent / ".env")

# 数据库连接参数（匹配你的pg15容器）
PG_USER = os.getenv("PG_USER", "root")
PG_PASSWORD = os.getenv("PG_PASSWORD", "123456")
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_DB = os.getenv("PG_DB", "interview_rag")

# 拼接连接串
DATABASE_URL = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"

# 创建带连接池的引擎（替代原生psycopg2.pool）
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_recycle=300
)

# 重写系统自检用的 init_pg() 函数，新增自动建表逻辑（解决上传表不存在）
def init_pg() -> bool:
    try:
        with engine.connect() as conn:
            # 连通测试
            conn.execute(text("SELECT 1"))

            # 自动创建上传任务表 upload_tasks
            create_task_sql = """
            CREATE TABLE IF NOT EXISTS upload_tasks (
                id VARCHAR(100) PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
            # 自动创建分片元数据表 chunk_meta
            create_chunk_sql = """
            CREATE TABLE IF NOT EXISTS chunk_meta (
                id SERIAL PRIMARY KEY,
                doc_id VARCHAR(100) NOT NULL,
                chunk_id VARCHAR(100) UNIQUE NOT NULL,
                content TEXT NOT NULL,
                tags JSON NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
            conn.execute(text(create_task_sql))
            conn.execute(text(create_chunk_sql))
            conn.commit()
        return True
    except Exception as e:
        print(f"PG连接/建表异常：{str(e)}")
        return False

# 兼容旧代码 get_conn（正确写法，with内部才是真实连接）
@contextmanager
def get_conn():
    real_conn = engine.connect()
    try:
        yield real_conn
    finally:
        real_conn.close()

# 空兼容函数，旧代码导入不会报错，无需手动调用关闭
def release_conn(conn):
    pass