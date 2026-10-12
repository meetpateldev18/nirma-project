"""
Call Script Writer Module — Turns a Free-Text Reason into a Call Script.

Staff no longer have to pick from a fixed list of pre-written call scripts. They type
the reason for the call in their own words (optionally attaching a supporting document
for extra context), and this module asks the configured LLM (local Ollama, falling back
to Groq Cloud) to write the system prompt that keeps the AI strictly on that topic for
the whole conversation. The opening greeting itself is built deterministically rather
than left to the LLM, so the mandatory AI self-disclosure (TRAI compliance) can never be
dropped or phrased ambiguously by a model.

If both the local and cloud LLM are unavailable (no model downloaded, no API key
configured — the common case on a fresh/local setup), a deterministic template stands in
so campaign creation never hard-fails for lack of AI infrastructure.

Upstream dependencies:
    - backend.ai_pipeline.llm (OllamaLLM, GroqLLM, FallbackLLM)
Downstream dependencies:
    - backend.api.campaigns (POST /api/campaigns/generate-script)
"""

import asyncio
import logging
from typing import Optional

from backend.ai_pipeline.llm import FallbackLLM, GroqLLM, OllamaLLM

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "gu": "Gujarati"}

OPENING_TEMPLATES = {
    "en": "Hello, this is an automated AI calling assistant from Nirma University. This call is regarding: {reason}.",
    "hi": "Namaste, main Nirma University ka automated AI calling assistant bol raha hoon. Yeh call iske baare mein hai: {reason}.",
    "gu": "Namaste, hu Nirma University no automated AI calling assistant chu. A call aa babate chhe: {reason}.",
}

# Max characters of an attached document fed into the generation prompt — keeps the
# meta-prompt small and fast regardless of how large a file staff attaches.
MAX_DOCUMENT_CHARS = 3000


def build_opening_message(reason: str, language: str) -> str:
    """
    Deterministically builds the mandatory AI-disclosure opening line.

    Args:
        reason: Free-text reason for the call, as typed by staff.
        language: Target language code ('en', 'hi', 'gu').

    Returns:
        str: Opening greeting, always starting by identifying the caller as an automated
            AI system, per TRAI consumer-disclosure requirements.
    """
    template = OPENING_TEMPLATES.get(language, OPENING_TEMPLATES["en"])
    return template.format(reason=reason.strip().rstrip(".!?"))


def _fallback_system_prompt(reason: str, language: str) -> str:
    """Deterministic system prompt used when no LLM is reachable to write one."""
    language_name = LANGUAGE_NAMES.get(language, "English")
    clean_reason = reason.strip().rstrip(".!?")
    return (
        f"You are an automated calling assistant for Nirma University. "
        f"The sole purpose of this call is: {clean_reason}. "
        f"Stay strictly on this topic for the entire call. If the caller asks about anything "
        f"unrelated, politely explain you can only help with this topic and redirect back to it. "
        f"Answer in a maximum of 2 short sentences (under 30 words). Never use markdown, bullet "
        f"points, or asterisks — this is a spoken phone call. Respond in {language_name}."
    )


async def generate_system_prompt(
    reason: str,
    language: str,
    document_text: Optional[str] = None,
) -> str:
    """
    Asks the configured LLM to write a topic-locked system prompt for this call's reason.

    Args:
        reason: Free-text reason for the call, as typed by staff.
        language: Target language code ('en', 'hi', 'gu').
        document_text: Optional extracted text from a staff-attached supporting document.

    Returns:
        str: A system prompt instructing the AI to stay strictly on the given reason.
            Falls back to a deterministic template if no LLM is reachable.
    """
    language_name = LANGUAGE_NAMES.get(language, "English")
    document_clause = (
        f"\n\nSupporting document the caller may ask about (use only what's relevant, "
        f"do not read it out verbatim):\n{document_text[:MAX_DOCUMENT_CHARS]}"
        if document_text
        else ""
    )
    meta_instructions = (
        "You write short operating instructions for an AI phone-calling assistant. "
        "Output ONLY the instructions themselves — no preamble, no quotation marks, no markdown."
    )
    task = (
        f'Write system instructions for an AI voice assistant whose ONLY purpose on this call is: '
        f'"{reason.strip()}".{document_clause}\n\n'
        f"The instructions must require the assistant to: stay strictly on this topic and this topic "
        f"only for the whole call; if asked about anything unrelated, politely decline and redirect "
        f"back to the topic above; answer in at most 2 short sentences, under 30 words; never use "
        f"markdown, bullet points, or asterisks since this is spoken audio; respond in {language_name}."
    )

    try:
        llm = FallbackLLM(OllamaLLM(), GroqLLM())
        generated = await asyncio.wait_for(llm.generate(meta_instructions, [], task), timeout=10.0)
        generated = (generated or "").strip()
        if len(generated) >= 20:
            logger.info("Generated custom call script via LLM for reason: '%s'", reason[:80])
            return generated
        logger.warning("LLM-generated script was too short/empty; using deterministic fallback.")
    except Exception as exc:
        logger.warning("Script generation via LLM failed (%s); using deterministic fallback.", exc)

    return _fallback_system_prompt(reason, language)


def extract_document_text(filename: str, raw_bytes: bytes) -> Optional[str]:
    """
    Best-effort plain-text extraction from an optional staff-uploaded supporting document.

    Supports .txt directly and .pdf via pypdf. Any failure (corrupt file, unsupported
    format, missing dependency) is swallowed and returns None — an attachment is always
    optional context, never a hard requirement for launching a call.

    Args:
        filename: Original uploaded filename, used to pick an extraction strategy.
        raw_bytes: Raw file contents.

    Returns:
        Optional[str]: Extracted text, or None if extraction wasn't possible.
    """
    lowered = filename.lower()
    try:
        if lowered.endswith(".txt") or lowered.endswith(".md"):
            return raw_bytes.decode("utf-8", errors="ignore").strip() or None

        if lowered.endswith(".pdf"):
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(raw_bytes))
            pages_text = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages_text).strip()
            return text or None
    except Exception as exc:
        logger.warning("Could not extract text from uploaded document '%s': %s", filename, exc)

    return None
