from fastapi import APIRouter
from pydantic import BaseModel
from config import settings

router = APIRouter(tags=["配置管理"])

@router.get("/config")
async def get_config():
    return {"data": settings.to_dict(), "flash_enabled": settings.is_flash_enabled()}

class ConfigSaveReq(BaseModel):
    data: dict

@router.post("/config/save")
async def save_config(req: ConfigSaveReq):
    settings.save_env(req.data)
    return {"msg": "配置已保存"}

@router.post("/config/reload")
async def reload_config():
    settings.reload()
    return {"msg": "环境变量已重载"}

@router.get("/system/status")
async def system_status():
    return {
        "pg": True,
        "milvus": True,
        "minio": True,
        "flash_enabled": settings.is_flash_enabled()
    }
