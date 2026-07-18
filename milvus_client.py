from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility, MilvusException
from config import settings, logger

# 全局固定连接别名
MILVUS_ALIAS = "default"
COLLECTION_NAME = None

def get_collection_name():
    global COLLECTION_NAME
    if not COLLECTION_NAME:
        COLLECTION_NAME = settings.get_env("MILVUS_COLLECTION", "interview_chunks")
    return COLLECTION_NAME

# 统一初始化连接，仅首次建立，重复调用不重复创建
def init_milvus_conn():
    if connections.has_connection(MILVUS_ALIAS):
        return True
    try:
        connections.connect(
            alias=MILVUS_ALIAS,
            host=settings.get_env("MILVUS_HOST", "127.0.0.1"),
            port=settings.get_env("MILVUS_PORT", "19530")
        )
        logger.info("Milvus 连接建立成功")
        return True
    except Exception as e:
        logger.error(f"Milvus连接失败: {e}")
        return False

# 废弃旧check_milvus，统一用init_milvus_conn
def check_milvus():
    return init_milvus_conn()

def get_collection():
    # 关键：先保证存在连接
    init_milvus_conn()
    name = get_collection_name()
    # 必须指定 using=MILVUS_ALIAS，否则找不到连接
    if not utility.has_collection(name, using=MILVUS_ALIAS):
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=100),
            FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="tags", dtype=DataType.JSON),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768)
        ]
        schema = CollectionSchema(fields, description="Interview RAG Chunks")
        col = Collection(name=name, schema=schema, using=MILVUS_ALIAS)
        index_params = {
            "metric_type": "L2",
            "index_type": "HNSW",
            "params": {"M": 8, "efConstruction": 64}
        }
        col.create_index(field_name="embedding", index_params=index_params)
        logger.info(f"Milvus 自动创建集合与索引: {name}")
        return col
    # 读取集合时指定连接别名
    col = Collection(name=name, using=MILVUS_ALIAS)
    col.load()
    return col

def init_milvus():
    if not init_milvus_conn():
        return False
    try:
        col = get_collection()
        logger.info("Milvus 集合加载完成")
        return True
    except MilvusException as e:
        logger.error(f"Milvus集合加载失败: {e}")
        return False

def rebuild_collection():
    init_milvus_conn()
    name = get_collection_name()
    try:
        if utility.has_collection(name, using=MILVUS_ALIAS):
            utility.drop_collection(name, using=MILVUS_ALIAS)
        get_collection()
        return True
    except MilvusException as e:
        logger.error(f"Milvus重建集合失败: {e}")
        return False