# 第一行必须写，阻断openai自动读取系统代理
import os
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("ALL_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("all_proxy", None)

from openai import AsyncOpenAI
from config import settings, logger

async def call_llm(prompt: str, use_flash: bool = False):
    if use_flash:
        key = settings.get_env("FLASH_API_KEY")
        base = settings.get_env("FLASH_API_BASE")
        # 修正环境变量名：FLASH_MODEL（和.env保持一致）
        model_name = settings.get_env("FLASH_MODEL")
    else:
        key = settings.get_env("PRO_API_KEY")
        base = settings.get_env("PRO_API_BASE_URL")
        # 修正环境变量名：PRO_MODEL
        model_name = settings.get_env("PRO_MODEL")

    # 校验模型名称非空，提前抛出友好提示
    if not model_name.strip():
        raise Exception("未配置FLASH_MODEL/PRO_MODEL模型名称，请检查.env配置")

    try:
        client = AsyncOpenAI(api_key=key, base_url=base, timeout=120)
        resp = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        content = resp.choices[0].message.content.strip()
        input_tokens = resp.usage.prompt_tokens
        output_tokens = resp.usage.completion_tokens
        cost = 0.0
        return content, input_tokens, output_tokens, cost
    except Exception as e:
        logger.error(f"LLM调用失败: {str(e)}")
        raise Exception(f"大模型请求异常：{str(e)}")