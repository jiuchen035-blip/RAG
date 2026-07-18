import os
import logging
from dotenv import load_dotenv, set_key
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

# 首次加载，override=True 强制覆盖系统环境变量
load_dotenv(dotenv_path=ENV_PATH, override=True)

class Config:
    def reload(self):
        """手动重载.env，修改配置后调用刷新"""
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        print("✅ .env 配置已重载")

    def get_env(self, key: str, default: str = "") -> str:
        val = os.getenv(key, default)
        return val.strip() if val else default

    @property
    def pg_dsn(self) -> str:
        user = self.get_env("PG_USER", "postgres")
        pwd = self.get_env("PG_PASSWORD", "postgres")
        host = self.get_env("PG_HOST", "127.0.0.1")
        port = self.get_env("PG_PORT", "5432")
        # 修复：变量名匹配.env PG_DB
        db = self.get_env("PG_DB", "interview_rag")
        return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

    def is_flash_enabled(self) -> bool:
        key_val = self.get_env("FLASH_API_KEY")
        return bool(key_val)

    def get_raw_env(self, key: str) -> str:
        """调试专用：直接打印读取到的原始值，排查URL为空/占位符问题"""
        val = self.get_env(key)
        print(f"[DEBUG ENV] {key} = {repr(val)}")
        return val

    def to_dict(self) -> dict:
        env_vars = {}
        if ENV_PATH.exists():
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip()
        return env_vars

    def save_env(self, data: dict):
        if not ENV_PATH.exists():
            ENV_PATH.touch()
        for k, v in data.items():
            set_key(str(ENV_PATH), k, str(v))
        self.reload()

settings = Config()

# 日志目录自动创建
log_dir = BASE_DIR / "logs"
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("rag_app")