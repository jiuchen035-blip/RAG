from minio import Minio
from minio.error import S3Error
from config import settings, logger

minio_client = None

def get_minio():
    global minio_client
    if not minio_client:
        minio_client = Minio(
            settings.get_env("MINIO_ENDPOINT", "127.0.0.1:9000"),
            access_key=settings.get_env("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=settings.get_env("MINIO_SECRET_KEY", "minioadmin"),
            secure=settings.get_env("MINIO_SECURE", "false").lower() == "true"
        )
    return minio_client

def check_minio():
    try:
        client = get_minio()
        client.list_buckets()
        return True
    except Exception as e:
        logger.error(f"MinIO连接失败: {e}")
        return False

def init_minio():
    if not check_minio():
        return False
    try:
        client = get_minio()
        bucket = settings.get_env("MINIO_BUCKET", "rag-files")
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info(f"MinIO 自动创建存储桶: {bucket}")
        return True
    except S3Error as e:
        logger.error(f"MinIO初始化失败: {e}")
        return False
