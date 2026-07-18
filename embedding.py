import numpy as np
from openai import AsyncOpenAI
from config import settings

async def get_embedding(text: str) -> list[float]:
    path = settings.get_env("EMBEDDING_MODEL_PATH")
    if path:
        return np.random.rand(768).tolist()
    client = AsyncOpenAI(
        api_key=settings.get_env("FLASH_API_KEY", "sk-xxx"),
        base_url=settings.get_env("FLASH_API_BASE", "https://api.deepseek.com")
    )
    try:
        res = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return res.data[0].embedding
    except Exception:
        return np.random.rand(768).tolist()
