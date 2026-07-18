from elasticsearch import Elasticsearch
from config import settings, logger

es_client = None

def get_es():
    global es_client
    if not es_client:
        host = settings.get_env("ES_HOST", "127.0.0.1")
        port = settings.get_env("ES_PORT", "9200")
        es_client = Elasticsearch([{"host": host, "port": int(port)}])
    return es_client

def check_es():
    try:
        es = get_es()
        return es.ping()
    except Exception as e:
        logger.error(f"Elasticsearch连接失败: {e}")
        return False

def init_es():
    if not check_es():
        return False
    try:
        es = get_es()
        if not es.indices.exists(index="interview_docs"):
            es.indices.create(index="interview_docs", body={
                "mappings": {
                    "properties": {
                        "doc_id": {"type": "keyword"},
                        "chunk_id": {"type": "keyword"},
                        "content": {"type": "text", "analyzer": "standard"},
                        "tags": {"type": "keyword"}
                    }
                }
            })
            logger.info("ES 自动创建索引: interview_docs")
        return True
    except Exception as e:
        logger.error(f"ES初始化失败: {e}")
        return False
