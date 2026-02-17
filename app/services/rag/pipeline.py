from typing import Dict, Any, List
from langchain_core.documents import Document

from app.core.llm import llm
from app.services.rag.store import retrieve

def _format_docs(docs: List[Document]) -> str:
    return "\n\n---\n\n".join(
        f"[source={d.metadata.get('source','?')}] {d.page_content}"
        for d in docs
    )

def answer(question: str, k: int = 5) -> Dict[str, Any]:
    docs = retrieve(question, k=k)
    context = _format_docs(docs)

    prompt = (
        "Du er en teknisk assistent.\n"
        "Svar kun på det brukeren spør om.\n"
        "Hvis spørsmålet gjelder ytelsesproblemer, inkluder kun problemer som eksplisitt handler om treghet, responstid eller skaleringsutfordringer.\n"
        "Ikke inkluder generelle feil eller funksjonsfeil.\n\n"
        f"Kontekst:\n{context}\n\n"
        f"Spørsmål: {question}\n"
    )

    resp = llm.invoke(prompt)

    return {
        "answer": resp.content,
        "sources": [d.metadata for d in docs],
    }
