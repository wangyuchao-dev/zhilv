from __future__ import annotations

from functools import lru_cache
from hashlib import md5

from app.config import (
    BACKEND_DIR,
    CHROMA_COLLECTION_NAME,
    CHROMA_DB_DIR,
    EMBEDDING_MODEL,
    LLM_API_KEY,
)


DATA_DIR = BACKEND_DIR / "data"


def _split_markdown_into_chunks(markdown_text: str, source_name: str) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    current_title = "文档开头"
    current_lines: list[str] = []

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            if current_lines:
                chunks.append(
                    {
                        "title": current_title,
                        "text": "\n".join(current_lines).strip(),
                        "source": source_name,
                    }
                )
                current_lines = []
            current_title = stripped.lstrip("#").strip()
        elif stripped:
            current_lines.append(stripped)

    if current_lines:
        chunks.append(
            {
                "title": current_title,
                "text": "\n".join(current_lines).strip(),
                "source": source_name,
            }
        )

    return chunks


def _build_chunk_id(source: str, title: str, text: str) -> str:
    digest = md5(f"{source}|{title}|{text}".encode("utf-8")).hexdigest()
    return f"{source}_{digest}"


def _build_document_text(chunk: dict[str, str]) -> str:
    return f"{chunk['title']}\n{chunk['text']}"


def load_guide_chunks() -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    for guide_file in sorted(DATA_DIR.glob("*.md*")):
        text = guide_file.read_text(encoding="utf-8")
        raw_chunks = _split_markdown_into_chunks(text, guide_file.name)
        for chunk in raw_chunks:
            chunks.append(
                {
                    "id": _build_chunk_id(chunk["source"], chunk["title"], chunk["text"]),
                    "title": chunk["title"],
                    "text": chunk["text"],
                    "source": chunk["source"],
                }
            )
    return chunks


@lru_cache(maxsize=1)
def _build_embeddings():
    """Embedding 实例全局只建一次。每次检索都新建要重新握手，实测慢 1-2 秒。"""
    if not LLM_API_KEY:
        print("[debug] LLM_API_KEY is empty")
        return None

    try:
        from langchain_community.embeddings.dashscope import DashScopeEmbeddings
    except ImportError:
        print("[debug] langchain_community DashScopeEmbeddings import failed")
        return None

    try:
        return DashScopeEmbeddings(
            model=EMBEDDING_MODEL,
            dashscope_api_key=LLM_API_KEY,
        )
    except Exception as e:
        print(f"[debug] DashScopeEmbeddings init failed: {e}")
        return None


@lru_cache(maxsize=1)
def _get_chroma_collection():
    """Chroma 客户端同理，PersistentClient 每次都打开 sqlite 文件很贵。"""
    try:
        import chromadb
    except ImportError:
        return None

    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_guide_chunks_to_chroma() -> int:
    embeddings = _build_embeddings()
    collection = _get_chroma_collection()
    chunks = load_guide_chunks()

    if embeddings is None:
        raise RuntimeError("当前环境缺少 embedding 能力，无法写入 Chroma。")
    if collection is None:
        raise RuntimeError("当前环境缺少 chromadb，无法写入 Chroma。")

    documents = [_build_document_text(chunk) for chunk in chunks]
    batch_size = 10
    vectors: list[list[float]] = []
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        vectors.extend(embeddings.embed_documents(batch))
    ids = [chunk["id"] for chunk in chunks]
    metadatas = [
        {
            "title": chunk["title"],
            "source": chunk["source"],
        }
        for chunk in chunks
    ]

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=vectors,
    )
    return len(chunks)


# ---------- 对外暴露，供检索层复用 ----------
# 这两个原本是私有函数。检索层要用同一套 embedding 模型和同一个 collection，
# 直接复用能保证「写进去的」和「查出来的」是同一个库、同一个向量空间。
build_embeddings = _build_embeddings
get_chroma_collection = _get_chroma_collection
