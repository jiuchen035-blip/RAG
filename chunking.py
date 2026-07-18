import re
import tiktoken
from config import settings

def chunk_by_markdown(text: str) -> list[str]:
    parts = re.split(r'(?m)^#{1,6}\s+', text)
    return [p.strip() for p in parts if p.strip()]

def chunk_by_fixed_length(text: str) -> list[str]:
    chunk_size = int(settings.get_env("RAG_CHUNK_SIZE", "800"))
    overlap = int(settings.get_env("RAG_CHUNK_OVERLAP", "100"))
    chunks, start = [], 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks

def chunk_by_code_isolation(text: str) -> list[str]:
    blocks = re.split(r'(?ms)(```.*?```)', text)
    chunks = []
    for b in blocks:
        if b.strip():
            if b.startswith("```"):
                chunks.append(b)
            else:
                chunks.extend(chunk_by_fixed_length(b))
    return chunks

def chunk_by_llm_semantic(text: str) -> list[str]:
    return chunk_by_fixed_length(text)

STRATEGIES = {
    "markdown": chunk_by_markdown,
    "fixed": chunk_by_fixed_length,
    "code": chunk_by_code_isolation,
    "semantic": chunk_by_llm_semantic,
}

def split_document(text: str, strategy: str = "markdown") -> list[str]:
    func = STRATEGIES.get(strategy, chunk_by_markdown)
    chunks = func(text)
    if not chunks:
        return []
    return chunks
