from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.chat import CriterionScore, FinishResponse, Source, StoredMessage
from models.scenario import Scenario
from services.openai_client import chat_complete_json, embed_query
from services.rag_store import search_similar

logger = logging.getLogger(__name__)

FEEDBACK_RAG_DOC_ID = os.getenv("FEEDBACK_RAG_DOC_ID", "samtalemetodikk_foreldre_rag.pdf")

EVAL_SYSTEM_PROMPT = """Du er en ekspert-evaluator for treningssamtaler mellom foreldre og barn.

Din oppgave er å evaluere samtalen mot 4 faste kriterier. \
Bruk fagdokumentene som kontekst og begrunnelsesgrunnlag, \
men kriteriene er alltid de samme uansett samtaleinnhold.

Returner ALLTID gyldig JSON i dette eksakte formatet (ingen annen tekst):
{
  "total_score": <heltall 0-100>,
  "criteria": [
    {
      "name": "empati",
      "score": <heltall 0-100>,
      "max_score": 100,
      "reason": "<i hvilken grad brukeren anerkjenner og validerer barnets følelser, med eksempel fra samtalen>"
    },
    {
      "name": "tydelighet",
      "score": <heltall 0-100>,
      "max_score": 100,
      "reason": "<i hvilken grad brukeren kommuniserer grenser og forventninger klart, med eksempel fra samtalen>"
    },
    {
      "name": "ro",
      "score": <heltall 0-100>,
      "max_score": 100,
      "reason": "<i hvilken grad brukeren holder seg rolig og unngår eskalering, med eksempel fra samtalen>"
    },
    {
      "name": "løsningsorientering",
      "score": <heltall 0-100>,
      "max_score": 100,
      "reason": "<i hvilken grad brukeren fokuserer på løsning fremfor konflikt, med eksempel fra samtalen>"
    }
  ],
  "positive_feedback": ["<konkret ting brukeren gjorde bra, henvis til faktisk melding>"],
  "negative_feedback": ["<konkret forbedringsområde med alternativt forslag til formulering>"]
}

Regler:
- Kriteriene er alltid disse 4, i denne rekkefølgen — ikke legg til eller fjern noen
- Selv om et kriterie ikke er relevant for scenarioet, sett score til 0 med en kort begrunnelse
- Gi minst 1 og maks 3 elementer i positive_feedback og negative_feedback
- Henvis alltid til noe brukeren faktisk skrev i samtalen
- total_score beregnes som gjennomsnittet av de fire score-verdiene (0-100)
- Fagdokumentene brukes kun som bakgrunnskunnskap for å begrunne vurderingene
"""


def _build_transcript(messages: list[StoredMessage]) -> str:
    lines = []
    for m in messages:
        role = "Bruker" if m.role == "user" else "AI-karakter"
        lines.append(f"{role}: {m.content}")
    return "\n".join(lines)


def _build_search_query(messages: list[StoredMessage]) -> str:
    user_msgs = [m.content for m in messages if m.role == "user"]
    return " ".join(user_msgs)


def _format_context(rows: list[Any]) -> str:
    if not rows:
        return "Ingen relevante fagdokumenter funnet."
    parts = []
    for r in rows:
        src = (r.meta or {}).get("source", r.doc_id)
        parts.append(f"[Kilde: {src}]\n{r.chunk_text}")
    return "\n\n---\n\n".join(parts)


def _safe_int(value: Any, default: int) -> int:
    """
    Safely convert a value to int, returning a default on failure.

    This protects against malformed model output (e.g. "5/10", null).
    """
    try:
        if value is None:
            raise ValueError("None is not a valid integer")
        return int(value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid integer value '%s' in evaluation response; using default %s",
            value,
            default,
        )
        return default


def _parse_response(data: dict, session_id: str, sources: list[Source]) -> FinishResponse:
    raw_criteria = data.get("criteria", [])
    criteria: list[CriterionScore] = []

    for c in raw_criteria:
        score = _safe_int(c.get("score"), 0)
        max_score = _safe_int(c.get("max_score"), 10)
        if max_score <= 0:
            logger.warning(
                "Non-positive max_score '%s' in evaluation response; using default 10",
                max_score,
            )
            max_score = 10

        criteria.append(
            CriterionScore(
                name=c.get("name", "Ukjent"),
                score=score,
                max_score=max_score,
                reason=c.get("reason", ""),
            )
        )

    if criteria:
        normalized_scores: list[float] = []
        for c in criteria:
            if c.max_score > 0:
                normalized_scores.append(c.score / c.max_score)
            else:
                logger.warning(
                    "Encountered criterion with non-positive max_score=%s; skipping in total_score",
                    c.max_score,
                )

        if normalized_scores:
            total_score = round(
                sum(normalized_scores) / len(normalized_scores) * 100
            )
        else:
            total_score = 0
    else:
        total_score = 0
    total_score = max(0, min(100, total_score))

    return FinishResponse(
        session_id=session_id,
        total_score=total_score,
        criteria=criteria,
        positive_feedback=data.get("positive_feedback", []),
        negative_feedback=data.get("negative_feedback", []),
        sources=sources,
    )


async def evaluate_conversation(
    session: AsyncSession,
    session_id: str,
    messages: list[StoredMessage],
    scenario: Scenario | None,
) -> FinishResponse:
    # 1. Bygg søkequery fra brukerens meldinger
    search_query = _build_search_query(messages)

    # 2. Hent relevante fagdokumenter fra pgvector
    rows = []
    if search_query.strip():
        try:
            q_emb = await embed_query(search_query)
            rows = await search_similar(
                session=session,
                query_embedding=q_emb,
                k=5,
                doc_id=FEEDBACK_RAG_DOC_ID,
            )
        except Exception:
            logger.warning("pgvector-søk feilet, fortsetter uten dokumentkontekst.", exc_info=True)

    context = _format_context(rows)

    # 3. Bygg evalueringsprompt
    scenario_info = ""
    if scenario:
        scenario_info = (
            f"Scenario: {scenario.title}\n"
            f"Beskrivelse: {scenario.description or ''}\n"
            f"Vanskelighetsgrad: {scenario.difficulty or ''}\n"
        )

    transcript = _build_transcript(messages)

    user_prompt = (
        f"{scenario_info}\n"
        f"Fagdokumenter (fasit):\n{context}\n\n"
        f"Samtale:\n{transcript}"
    ).strip()

    # 4. Kall OpenAI med JSON mode
    try:
        data = await chat_complete_json(system=EVAL_SYSTEM_PROMPT, user=user_prompt)
    except Exception as e:
        logger.error("OpenAI evaluering feilet: %s", e)
        raise

    # 5. Bygg sources fra retrievede dokumenter
    sources = [
        Source(
            source=(r.meta or {}).get("source", r.doc_id),
            doc_id=r.doc_id,
            chunk_id=r.id,
            meta=r.meta or {},
        )
        for r in rows
    ]

    return _parse_response(data, session_id, sources)
