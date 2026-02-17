from __future__ import annotations

import os
from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.llm import embeddings

splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)

FAISS_PATH = "vectorstore"  # lagres i prosjektroten
_vectorstore: Optional[FAISS] = None


def _load_if_exists() -> Optional[FAISS]:
    if os.path.exists(FAISS_PATH):
        return FAISS.load_local(
            FAISS_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
    return None


def _ensure_loaded():
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = _load_if_exists()


def ingest_texts(items: List[Dict[str, Any]]) -> int:
    global _vectorstore
    _ensure_loaded()

    docs: List[Document] = []
    for it in items:
        content = it["content"]
        meta = it.get("metadata", {})
        for chunk in splitter.split_text(content):
            docs.append(Document(page_content=chunk, metadata=meta))

    if _vectorstore is None:
        _vectorstore = FAISS.from_documents(docs, embeddings)
    else:
        _vectorstore.add_documents(docs)

    _vectorstore.save_local(FAISS_PATH)
    return len(docs)


def retrieve(question: str, k: int = 5) -> List[Document]:
    _ensure_loaded()
    if _vectorstore is None:
        raise RuntimeError("Vector store er tom. Kjør /rag/ingest først.")

    retriever = _vectorstore.as_retriever(search_kwargs={"k": k})
    return retriever.invoke(question)
