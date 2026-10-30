"""
Call Script Writer Module — Turns Free-Text Reasons & Supporting Documents into Rich Call Scripts.

Staff type the objective or reason for the call in their own words and optionally attach
an official circular or notice document (.pdf, .docx, .txt). This module orchestrates
cloud/local LLM inference (Groq, Gemini, local Ollama) to synthesize:
1. A natural, TRAI-compliant opening greeting in the target language (Gujarati, Hindi, English).
2. A comprehensive, topic-locked voice system prompt that grounds the AI in all verified
   details from the attached circular (what the report is, report format, required sections,
   submission portal, deadlines, penalties) while enforcing strict telephony SLA constraints
   (<35 words per spoken turn).

Upstream dependencies:
    - backend.config.settings
    - pypdf >= 5.0
    - python-docx >= 1.0
    - httpx >= 0.27

Downstream dependencies:
    - backend.api.campaigns (POST /api/campaigns/generate-script)
"""

import asyncio
import io
import json
import logging
import re
from typing import Optional, Tuple

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "gu": "Gujarati"}

# Max characters of an attached document fed into the generation prompt
MAX_DOCUMENT_CHARS = 15000

# TRAI-mandated disclosure prefixes per language
TRAI_DISCLOSURES = {
    "gu": "નમસ્તે, હું નિર્મા યુનિવર્સિટીમાંથી ઓટોમેટેડ AI કૉલિંગ આસિસ્ટન્ટ બોલું છું.",
    "hi": "नमस्ते, मैं निरમા विश्वविद्यालय से एक स्वचालित AI कॉलिंग सहायक बोल रहा हूँ।",
    "en": "Hello, this is an automated AI calling assistant from Nirma University.",
}


def _clean_reason(reason: str) -> str:
    """
    Cleans raw operator shorthand and special symbols from staff-entered reasons.

    Args:
        reason: Raw reason string typed by staff.

    Returns:
        str: Cleaned, human-readable reason string.
    """
    cleaned = reason.strip()
    # Remove operator delimiters like >, <, ->
    cleaned = re.sub(r"\s*[><-]+\s*", " ", cleaned)
    # Remove common operator prefixes like "reminder:", "tell him:", "calling regarding:"
    cleaned = re.sub(r"^(?:calling\s+(?:him|her|them|student)?\s*(?:regarding|about)?\s*[:,-]?\s*)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:reminder\s*[:,-]\s*)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:urgent\s*[:,-]\s*)", "", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split()).strip()


def _build_deterministic_opening(reason: str, language: str) -> str:
    """
    Deterministically builds a natural, TRAI-compliant opening line.

    Args:
        reason: Cleaned reason for the call.
        language: Target language code ('en', 'hi', 'gu').

    Returns:
        str: Politely formatted opening greeting adhering to TRAI standards.
    """
    clean = _clean_reason(reason)
    if language == "gu":
        return f"{TRAI_DISCLOSURES['gu']} આ કૉલ તમને {clean} અંગે યાદ અપાવવા માટે કરવામાં આવ્યો છે."
    elif language == "hi":
        return f"{TRAI_DISCLOSURES['hi']} यह कॉल आपको {clean} के संबंध में सूचित करने के लिए है।"
    else:
        return f"{TRAI_DISCLOSURES['en']} I am calling to remind you regarding {clean}."


def _build_deterministic_system_prompt(
    reason: str,
    language: str,
    document_text: Optional[str] = None,
) -> str:
    """
    Deterministic fallback system prompt incorporating circular facts and telephony rules.

    Args:
        reason: Free-text reason for the call.
        language: Target language code ('en', 'hi', 'gu').
        document_text: Optional extracted text from an attached supporting document.

    Returns:
        str: Topic-locked system prompt grounding the assistant in circular context.
    """
    clean = _clean_reason(reason)
    language_name = LANGUAGE_NAMES.get(language, "English")

    doc_section = ""
    if document_text and document_text.strip():
        doc_section = (
            f"\n\nVERIFIED CIRCULAR & NOTICE DETAILS (ACCURATELY ANSWER STUDENT QUESTIONS FROM THIS):\n"
            f"{document_text[:MAX_DOCUMENT_CHARS]}\n"
        )

    return (
        f"You are the official AI voice representative of Nirma University.\n"
        f"The primary purpose of this call is: {clean}.\n"
        f"You must converse politely and clearly in {language_name}.\n"
        f"{doc_section}\n"
        f"CRITICAL VOICE CALL RULES & BOUNDARIES:\n"
        f"1. BREVITY (VOICE SLA): Each spoken answer must be at most 1 to 2 short sentences (strictly under 35 words).\n"
        f"2. TOPIC BOUNDARY: Stay strictly locked to this notice and the circular above. Politely deflect unrelated questions.\n"
        f"3. ANTI-HALLUCINATION: Never guess or invent details not present in the verified context. Advise checking nirmauni.ac.in or contacting the department office.\n"
        f"4. SPOKEN FORMATTING: Never use markdown, bullet points, asterisks, numbered lists, or raw symbols."
    )


def extract_document_text(filename: str, raw_bytes: bytes) -> Optional[str]:
    """
    Extracts structured plain text from an optional staff-uploaded supporting document.

    Supports .txt, .md, .csv, .pdf (via pypdf), and .docx (via python-docx including tables).
    Any extraction failure is safely caught, logged, and returns None.

    Args:
        filename: Original uploaded filename.
        raw_bytes: Raw file byte stream.

    Returns:
        Optional[str]: Extracted document text, or None if extraction was not possible.
    """
    if not filename or not raw_bytes:
        return None

    lowered = filename.lower()
    try:
        # 1. Plain text / Markdown / CSV
        if lowered.endswith((".txt", ".md", ".csv", ".rtf")):
            for encoding in ("utf-8", "latin-1", "cp1252"):
                try:
                    text = raw_bytes.decode(encoding).strip()
                    if text:
                        return text[:MAX_DOCUMENT_CHARS]
                except UnicodeDecodeError:
                    continue

        # 2. PDF Documents
        if lowered.endswith(".pdf"):
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw_bytes))
            pages_text = []
            for i, page in enumerate(reader.pages):
                page_str = (page.extract_text() or "").strip()
                if page_str:
                    pages_text.append(f"[Page {i+1}]\n{page_str}")
            extracted = "\n\n".join(pages_text).strip()
            if extracted:
                logger.info("Successfully extracted %d characters from PDF: '%s'", len(extracted), filename)
                return extracted[:MAX_DOCUMENT_CHARS]

        # 3. Microsoft Word (.docx) Documents
        if lowered.endswith((".docx", ".doc")):
            import docx

            doc = docx.Document(io.BytesIO(raw_bytes))
            text_parts = []

            # Extract paragraph headings and body text
            for p in doc.paragraphs:
                p_text = p.text.strip()
                if p_text:
                    text_parts.append(p_text)

            # Extract structured table contents (e.g. rubrics, schedules, section guidelines)
            for tbl in doc.tables:
                for row in tbl.rows:
                    row_str = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_str:
                        text_parts.append(row_str)

            extracted = "\n".join(text_parts).strip()
            if extracted:
                logger.info("Successfully extracted %d characters from DOCX: '%s'", len(extracted), filename)
                return extracted[:MAX_DOCUMENT_CHARS]

    except Exception as exc:
        logger.warning("Could not extract text from uploaded document '%s': %s", filename, exc)

    return None


async def generate_call_script(
    reason: str,
    language: str,
    document_text: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Synthesizes a TRAI-compliant opening line and an attached-document-grounded system prompt.

    Orchestrates LLM inference across Groq Cloud, Local Ollama, and Google Gemini with
    failover to a robust deterministic template.

    Args:
        reason: Staff-entered reason or notes for the call.
        language: Target language code ('en', 'hi', 'gu').
        document_text: Optional extracted text from an attached circular or guidelines file.

    Returns:
        Tuple[str, str]: (opening_message, system_prompt).
    """
    language_name = LANGUAGE_NAMES.get(language, "English")
    clean = _clean_reason(reason)

    doc_clause = ""
    if document_text and document_text.strip():
        doc_clause = (
            f"\n\nATTACHED OFFICIAL CIRCULAR / GUIDELINES DOCUMENT:\n"
            f"```\n{document_text[:MAX_DOCUMENT_CHARS]}\n```\n"
        )

    system_instruction = (
        "You are the Lead Telephony AI Architect for Nirma University. "
        "Generate a structured JSON object with exactly two string fields:\n"
        '1. "opening_message": The opening greeting spoken by the AI as soon as the student answers the call.\n'
        "   - MANDATORY TRAI REGULATION: Sentence 1 MUST explicitly identify as an automated AI calling assistant of Nirma University.\n"
        "   - Sentence 2: Politely state the reason for calling in natural spoken language (rephrasing any rough operator shorthand or symbols into clean polite speech).\n"
        f"   - Target Language: {language_name}. If Gujarati, use natural, grammatically correct Gujarati script.\n"
        "   - Length: Strictly 1 to 2 short sentences.\n\n"
        '2. "system_prompt": The comprehensive operating system prompt grounding the voice assistant during the phone conversation.\n'
        "   - Identity: Polite, official AI voice representative of Nirma University.\n"
        f"   - Response Language: Must converse in {language_name}.\n"
        "   - VERIFIED KNOWLEDGE BASE: If an attached document is provided, you MUST extract and embed all verified details so the AI can accurately answer questions like 'what is this report?', 'what does it look like / format?', 'where do I submit?', 'what is the deadline?', and 'what are the penalties?'.\n"
        "   - TELEPHONY VOICE SLA RULES: Each spoken response during the call must be at most 1 to 2 short sentences (under 35 words). Strictly topic-locked; politely deflect unrelated questions. Never guess facts not in the context; no markdown or bullet points in spoken output.\n\n"
        'Output strictly valid JSON with keys "opening_message" and "system_prompt". Do not wrap in markdown or backticks.'
    )

    user_prompt = (
        f'Staff Call Objective / Reason:\n"{reason}"\n\n'
        f"Target Language: {language_name} ({language})\n"
        f"{doc_clause}"
    )

    # 1. Attempt Groq Cloud (sub-second high capability multilingual reasoning)
    if settings.groq_api_key and not settings.groq_api_key.startswith("your_"):
        try:
            headers = {
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "qwen/qwen3.8-27b",
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=2.5)) as client:
                resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
                if resp.status_code == 200:
                    raw_content = resp.json()["choices"][0]["message"]["content"]
                    data = json.loads(raw_content)
                    opening = data.get("opening_message", "").strip()
                    prompt = data.get("system_prompt", "").strip()
                    if opening and prompt:
                        opening = _ensure_trai_disclosure(opening, language)
                        logger.info("Successfully synthesized call script bundle via Groq Cloud (Qwen-27B)")
                        return opening, prompt
        except Exception as exc:
            logger.warning("Groq Cloud script synthesis failed: %s. Falling back...", exc)

    # 2. Attempt Google Gemini Cloud
    if settings.gemini_api_key and not settings.gemini_api_key.startswith("your_"):
        for model_name in [settings.gemini_model, settings.gemini_fallback_model, "gemini-2.5-flash", "gemini-1.5-flash"]:
            if not model_name:
                continue
            try:
                gemini_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={settings.gemini_api_key}"
                payload = {
                    "system_instruction": {"parts": [{"text": system_instruction}]},
                    "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.2,
                    },
                }
                async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=2.5)) as client:
                    resp = await client.post(gemini_endpoint, json=payload)
                    if resp.status_code == 200:
                        raw_content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                        data = json.loads(raw_content)
                        opening = data.get("opening_message", "").strip()
                        prompt = data.get("system_prompt", "").strip()
                        if opening and prompt:
                            opening = _ensure_trai_disclosure(opening, language)
                            logger.info("Successfully synthesized call script bundle via Gemini (%s)", model_name)
                            return opening, prompt
            except Exception as exc:
                logger.warning("Gemini script synthesis (%s) failed: %s. Trying next tier...", model_name, exc)

    # 3. Deterministic Safety Fallback
    logger.info("Using deterministic script generation fallback.")
    opening = _build_deterministic_opening(reason, language)
    prompt = _build_deterministic_system_prompt(reason, language, document_text)
    return opening, prompt


def _ensure_trai_disclosure(opening: str, language: str) -> str:
    """
    Defensively verifies that the opening line explicitly includes the university and AI identity.

    Args:
        opening: LLM-generated opening greeting.
        language: Target language code.

    Returns:
        str: Guaranteed TRAI-compliant opening greeting.
    """
    lowered = opening.lower()
    has_nirma = "nirma" in lowered or "નિર્મા" in opening or "निरमा" in opening
    has_ai = "ai" in lowered or "એઆઈ" in opening or "एआई" in opening or "automated" in lowered or "સ્વચાલિત" in opening

    if not (has_nirma and has_ai):
        disclosure = TRAI_DISCLOSURES.get(language, TRAI_DISCLOSURES["en"])
        return f"{disclosure} {opening}".strip()

    return opening


# ------------------------------------------------------------------------------
# Backward Compatibility Wrappers
# ------------------------------------------------------------------------------
def build_opening_message(reason: str, language: str) -> str:
    """Synchronous fallback wrapper for building the TRAI opening line."""
    return _build_deterministic_opening(reason, language)


async def generate_system_prompt(
    reason: str,
    language: str,
    document_text: Optional[str] = None,
) -> str:
    """Asynchronous wrapper returning the system prompt."""
    _, prompt = await generate_call_script(reason, language, document_text)
    return prompt
