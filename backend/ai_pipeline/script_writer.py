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
    """Deterministic, boundary-enforced voice system prompt for Nirma University call campaigns."""
    language_name = LANGUAGE_NAMES.get(language, "English")
    clean_reason = reason.strip().rstrip(".!?")

    if language == "gu":
        return (
            f"તમે નિર્મા યુનિવર્સિટીના સત્તાવાર AI વોઈસ આસિસ્ટન્ટ છો. "
            f"આ કૉલનો એકમાત્ર હેતુ છે: {clean_reason}. "
            f"સમગ્ર કૉલ દરમિયાન ફક્ત આ સૂચના પર જ વાત કરો. "
            f"જો વિદ્યાર્થી કોઈ અન્ય વિષય અથવા સામાન્ય જ્ઞાન પૂછે, તો નમ્રતાપૂર્વક જણાવો કે તમે ફક્ત આ સૂચના માટે જ સહાય કરી શકો છો. "
            f"જવાબ મહત્તમ 1 થી 2 ટૂંકા વાક્યોમાં (30 શબ્દોથી ઓછા) આપો. કોઈ માર્કડાઉન, બુલેટ પોઇન્ટ કે ફૂદડીનો ઉપયોગ કરવો નહીં."
        )
    elif language == "hi":
        return (
            f"आप निरमा विश्वविद्यालय के आधिकारिक AI वॉइस असिस्टेंट हैं। "
            f"इस कॉल का एकमात्र उद्देश्य है: {clean_reason}। "
            f"पूरी कॉल के दौरान सख्ती से इसी सूचना पर केंद्रित रहें। "
            f"यदि कॉलर किसी असंबंधित विषय या सामान्य ज्ञान के बारे में पूछता है, तो विनम्रता से बताएं कि आप केवल इस सूचना में सहायता कर सकते हैं। "
            f"उत्तर अधिकतम 1 से 2 छोटे वाक्यों में (30 शब्दों से कम) दें। कभी भी मार्कडाउन, बुलेट पॉइंट्स या विशेष चिह्नों का उपयोग न करें।"
        )
    else:
        return (
            f"You are the official AI voice assistant for Nirma University. "
            f"The sole purpose of this call is: {clean_reason}. "
            f"Stay strictly on this topic for the entire conversation. "
            f"If the caller asks about anything unrelated, politely explain that you can only assist with this notice, and redirect back. "
            f"If you do not know a specific detail, advise checking nirmauni.ac.in or the Student Section. "
            f"Answer in a maximum of 2 short sentences (strictly under 30 words). "
            f"Never use markdown, bullet points, or asterisks — this is spoken audio. "
            f"Respond clearly in {language_name}."
        )


async def generate_system_prompt(
    reason: str,
    language: str,
    document_text: Optional[str] = None,
) -> str:
    """
    Asks the configured LLM to write a topic-locked, boundary-enforced system prompt for this call's reason.

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
        "You write production operating instructions for an enterprise AI phone-calling assistant representing Nirma University. "
        "Output ONLY the system prompt itself — no conversational preamble, no quotation marks, no markdown symbols."
    )
    task = (
        f'Write system instructions for a Nirma University AI voice assistant whose ONLY purpose on this call is: '
        f'"{reason.strip()}".{document_clause}\n\n'
        f"CRITICAL REQUIREMENTS:\n"
        f"1. Identity: The assistant must act as a polite, helpful, official representative of Nirma University.\n"
        f"2. Strict Boundaries: Stay locked onto this topic. If asked anything out-of-scope (general knowledge, coding, politics, personal advice), politely deflect back to this notice.\n"
        f"3. Anti-Hallucination: Never guess missing facts; advise verifying on nirmauni.ac.in or with the Student Section.\n"
        f"4. Brevity (Voice SLA): Responses must be at most 1 to 2 short sentences (strictly under 30 words).\n"
        f"5. Spoken Style: Prohibit all markdown formatting, asterisks, bullet points, or numbered lists.\n"
        f"6. Language: The assistant must respond in {language_name}."
    )

    try:
        llm = FallbackLLM()
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
