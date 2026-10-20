"""
Language Model (LLM) Module — Abstract Adapters, Local Ollama & Groq Cloud Failover.

This module provides conversational reasoning for phone dialogue turns.
It orchestrates context-aware prompt construction, conversational history pruning,
and latency-bounded LLM generation:
- Primary: Qwen-14B (Ollama Q4_K_M) running locally on server GPU.
- Fallback: Groq Cloud API (LLaMA-3.3-70B) offering sub-second response times.

Invariants:
    - Conversational responses must remain under 35 words (<= 2 sentences) for voice UX.
    - History must be truncated to the last 6 messages (3 turns) to maintain low TTFT.
    - No markdown formatting, bullet points, asterisks, or lists in generated speech text.

Dependencies:
    - httpx >= 0.27
    - pydantic >= 2.0
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

# Mandatory Telephony Guardrail appended to all LLM system prompts
TELEPHONY_VOICE_CONSTRAINT = (
    "\n\nCRITICAL VOICE CALL RULES: "
    "1. Speak naturally as if talking on a real telephone call. "
    "2. Keep your answer strictly under 2 short sentences (maximum 30 words). "
    "3. NEVER use markdown symbols, bold text, bullet points, asterisks, or numbered lists. "
    "4. Reply in the exact same language as the caller (Hindi, Gujarati, or English)."
)


class LLMAdapter(ABC):
    """
    Abstract interface for conversational Language Model engines.

    All implementations must be non-blocking and asynchronously compliant.
    """

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        user_input: str,
    ) -> str:
        """
        Generates the next conversational voice turn response.

        Args:
            system_prompt: Campaign-specific prompt defining role and business logic.
            history: List of prior turns formatted as [{'role': 'user'|'assistant', 'content': '...'}].
            user_input: Latest transcribed speech from the caller.

        Returns:
            str: Concise textual response ready for speech synthesis.

        Raises:
            LLMException: If inference fails across retries.
        """
        pass


class OllamaLLM(LLMAdapter):
    """
    Primary local LLM adapter communicating with the Ollama daemon over HTTP.

    Executes quantized Qwen-14B models on the server's local NVIDIA GPU,
    ensuring private student records never leave the university infrastructure.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 4.0,
    ) -> None:
        """
        Initializes the Ollama LLM adapter.

        Args:
            base_url: HTTP endpoint of Ollama service (default from settings).
            model: Tagged model identifier (default: 'qwen3:14b').
            timeout_seconds: HTTP network timeout threshold.
        """
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout_seconds = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None
        self._quota_exhausted_until: float = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        """Returns or lazily creates a persistent pooled AsyncClient for local Ollama."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds, connect=1.5),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            )
        return self._client

    async def aclose(self) -> None:
        """Gracefully closes persistent HTTP connection pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def generate(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        user_input: str,
    ) -> str:
        """
        Submits a multi-turn chat completion request to the local Ollama API.

        Args:
            system_prompt: Base campaign instructions.
            history: Prior conversational message list.
            user_input: Current user utterance transcript.

        Returns:
            str: Synthesizable text answer.

        Raises:
            httpx.HTTPError: If the Ollama server returns an error code or times out.
        """
        full_system_prompt = f"{system_prompt}{TELEPHONY_VOICE_CONSTRAINT}"
        messages: List[Dict[str, str]] = [{"role": "system", "content": full_system_prompt}]

        # Telephony optimization: Keep only last 6 messages (3 conversational exchanges)
        pruned_history = history[-6:] if history else []
        messages.extend(pruned_history)
        messages.append({"role": "user", "content": user_input})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 75,  # Strictly limit token count to prevent long generation
            },
        }

        endpoint = f"{self.base_url}/api/chat"
        client = await self._get_client()
        resp = await client.post(endpoint, json=payload)
        resp.raise_for_status()
        data = resp.json()
        message_obj = data.get("message", {})
        raw_content = message_obj.get("content", "").strip()

        # Clean any inadvertent markdown asterisks
        return raw_content.replace("*", "").replace("#", "").strip()


class GroqLLM(LLMAdapter):
    """
    Cloud fallback LLM adapter communicating with the Groq Cloud API.

    Leverages Groq's LPU architecture to achieve sub-second Time-to-First-Token (TTFT)
    on high-capability open-weight models (LLaMA-3.3-70B).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen/qwen3.8-27b",
        timeout_seconds: float = 5.0,
    ) -> None:
        """
        Initializes the Groq LLM adapter.

        Args:
            api_key: Groq Cloud API secret key.
            model: Target model identifier on Groq infrastructure.
            timeout_seconds: Network request timeout.
        """
        self.api_key = api_key if api_key is not None else settings.groq_api_key
        self.model = model
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"
        self.timeout_seconds = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None
        self._quota_exhausted_until: float = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        """Returns or lazily creates a persistent pooled AsyncClient for Groq Cloud."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds, connect=2.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            )
        return self._client

    async def aclose(self) -> None:
        """Gracefully closes persistent HTTP connection pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def generate(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        user_input: str,
    ) -> str:
        """
        Dispatches chat completion request to Groq Cloud API.

        Args:
            system_prompt: Base campaign instructions.
            history: Conversation turn history.
            user_input: Current user utterance.

        Returns:
            str: Generated conversational response.

        Raises:
            ValueError: If GROQ_API_KEY is missing.
            httpx.HTTPError: If the remote API fails.
        """
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not configured in environment variables.")

        full_system_prompt = f"{system_prompt}{TELEPHONY_VOICE_CONSTRAINT}"
        messages: List[Dict[str, str]] = [{"role": "system", "content": full_system_prompt}]
        messages.extend(history[-6:] if history else [])
        messages.append({"role": "user", "content": user_input})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 100,
            "temperature": 0.3,
        }

        client = await self._get_client()
        resp = await client.post(self.endpoint, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return content.replace("*", "").replace("#", "").strip()


class GeminiLLM(LLMAdapter):
    """
    Google Gemini Cloud LLM Adapter (e.g. Gemini 3.8 Flash, 2.5 Flash, 1.5 Flash).

    Leverages Google's Generative Language API with low-latency REST endpoints.
    Provides native multilingual conversational fluency across Hindi, Gujarati, and English.
    """

    _quota_exhausted_until: float = 0.0

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 4.0,
    ) -> None:
        """
        Initializes the Gemini LLM adapter.

        Args:
            api_key: Google Gemini API key (defaults to settings.gemini_api_key).
            model: Target Gemini model identifier (defaults to settings.gemini_model).
            timeout_seconds: Network request timeout.
        """
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.timeout_seconds = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Returns or lazily creates a persistent pooled AsyncClient for Gemini."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds, connect=2.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            )
        return self._client

    async def aclose(self) -> None:
        """Gracefully closes persistent HTTP connection pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def generate(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        user_input: str,
    ) -> str:
        """
        Submits chat prompt to Google Gemini API and returns conversational reply.

        Args:
            system_prompt: Base campaign instructions.
            history: Message history.
            user_input: User speech input.

        Returns:
            str: Concise textual reply ready for voice synthesis.

        Raises:
            ValueError: If GEMINI_API_KEY is not configured.
            httpx.HTTPError: If the remote API fails.
        """
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured in environment variables.")

        if time.monotonic() < GeminiLLM._quota_exhausted_until:
            raise RuntimeError("Gemini LLM quota circuit breaker active (429 rate limit).")

        full_system_prompt = f"{system_prompt}{TELEPHONY_VOICE_CONSTRAINT}"

        # Format messages for Gemini generateContent API
        contents = []
        for msg in (history[-6:] if history else []):
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
        contents.append({"role": "user", "parts": [{"text": user_input}]})

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": full_system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": 60,
                "temperature": 0.2,
            },
        }

        client = await self._get_client()
        try:
            resp = await client.post(endpoint, json=payload)
            if resp.status_code == 429:
                GeminiLLM._quota_exhausted_until = time.monotonic() + 300.0
                raise RuntimeError(f"Gemini LLM quota exceeded (429): {resp.text[:150]}")
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                GeminiLLM._quota_exhausted_until = time.monotonic() + 300.0
            raise

        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError(f"Gemini API returned no candidates: {data}")

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise ValueError(f"Gemini API returned empty parts: {data}")

        text = parts[0].get("text", "")
        return text.replace("*", "").replace("#", "").strip()


class RuleBasedLLM(LLMAdapter):
    """
    Deterministic rule-based fallback when all cloud and local inference engines fail.
    Multilingual, context-aware, and polite telecom response.
    """

    async def generate(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        user_input: str,
    ) -> str:
        """
        Returns a polite, deterministic notice matching the conversation's target language.
        """
        prompt_lower = system_prompt.lower()

        # Check for Gujarati (either language code, prompt indication, or script)
        is_gujarati = (
            "gujarati" in prompt_lower
            or "language: gu" in prompt_lower
            or "respond in gujarati" in prompt_lower
            or any("\u0A80" <= c <= "\u0AFF" for c in user_input)
            or any("\u0A80" <= c <= "\u0AFF" for c in system_prompt)
        )
        # Check for Hindi
        is_hindi = (
            "hindi" in prompt_lower
            or "language: hi" in prompt_lower
            or "respond in hindi" in prompt_lower
            or any("\u0900" <= c <= "\u097F" for c in user_input)
            or any("\u0900" <= c <= "\u097F" for c in system_prompt)
        )

        if is_gujarati:
            return "હું નિર્મા યુનિવર્સિટીનો AI સહાયક છું અને ફક્ત આ સૂચના અને પરીક્ષા સંબંધિત માહિતી આપી શકું છું. પરીક્ષા અંગે કોઈ પ્રશ્ન હોય તો પૂછો."
        elif is_hindi:
            return "मैं निरमा विश्वविद्यालय का AI सहायक हूँ और केवल इस सूचना व परीक्षा संबंधी प्रश्नों में सहायता कर सकता हूँ। क्या आपका कोई प्रश्न है?"
        else:
            return "I am an automated AI assistant for Nirma University and can only answer queries related to this official notice. How can I assist you regarding this?"


class FallbackLLM(LLMAdapter):
    """
    Composite LLM adapter providing multi-tier automatic failover across
    Local Ollama -> Groq Cloud -> Gemini Flash -> Rule-Based.

    Includes circuit breaker on local Ollama to guarantee < 1.5s conversational turn budget.
    """

    _ollama_offline_until: float = 0.0

    def __init__(
        self,
        primary: Optional[LLMAdapter] = None,
        fallback: Optional[LLMAdapter] = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        """
        Initializes the FallbackLLM composite cascade.

        Args:
            primary: Primary LLM adapter override.
            fallback: Explicit fallback LLM adapter override.
            timeout_seconds: Execution deadline per tier before triggering next fallback (default: 2.0s).
        """
        self.timeout_seconds = timeout_seconds
        self.chain: List[LLMAdapter] = []

        if primary is not None:
            self.chain.append(primary)
        else:
            # 1. Local GPU Ollama if running on HPC supercomputer (with circuit breaker)
            self.chain.append(OllamaLLM())
            # 2. Groq Cloud (ultra low-latency LLaMA-3.3-70b / Qwen - sub-500ms voice inference)
            if settings.groq_api_key and not settings.groq_api_key.startswith("your_"):
                self.chain.append(GroqLLM(timeout_seconds=2.0))
            # 3. Google Gemini Cloud reasoning
            if settings.gemini_api_key and not settings.gemini_api_key.startswith("your_"):
                self.chain.append(GeminiLLM(model=settings.gemini_model, timeout_seconds=1.5))
                if settings.gemini_fallback_model:
                    self.chain.append(GeminiLLM(model=settings.gemini_fallback_model, timeout_seconds=1.5))

        if fallback is not None:
            self.chain.append(fallback)
        else:
            # 4. Deterministic multilingual rule-based template
            self.chain.append(RuleBasedLLM())

        # Retain backward compatibility attributes
        self.primary = self.chain[0]
        self.fallback = self.chain[1] if len(self.chain) > 1 else self.chain[0]

    async def generate(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        user_input: str,
    ) -> str:
        """
        Executes bounded LLM generation across the cascade until a valid response is generated.

        Args:
            system_prompt: Base campaign instructions.
            history: Message history.
            user_input: User speech input.

        Returns:
            str: Synthesizable response text.
        """
        now = time.monotonic()
        for i, adapter in enumerate(self.chain):
            adapter_name = adapter.__class__.__name__
            model_info = getattr(adapter, "model", "")

            # Circuit breaker: skip Ollama if it recently failed
            if isinstance(adapter, OllamaLLM) and now < FallbackLLM._ollama_offline_until:
                continue

            t0 = time.monotonic()
            try:
                # Local Ollama gets a tight 0.5s connection deadline so offline state doesn't delay voice turns
                timeout = 0.5 if isinstance(adapter, OllamaLLM) else self.timeout_seconds
                reply = await asyncio.wait_for(
                    adapter.generate(system_prompt, history, user_input),
                    timeout=timeout,
                )
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                logger.info("LLM tier %d (%s %s) succeeded in %d ms", i + 1, adapter_name, model_info, elapsed_ms)
                return reply
            except Exception as exc:
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                if isinstance(adapter, OllamaLLM):
                    FallbackLLM._ollama_offline_until = time.monotonic() + 60.0  # Trip circuit breaker for 60s
                logger.warning(
                    "LLM tier %d (%s %s) failed in %d ms: %s. Advancing to next fallback tier...",
                    i + 1,
                    adapter_name,
                    model_info,
                    elapsed_ms,
                    exc,
                )

        # Ultimate deterministic safety guarantee (language aware)
        return await RuleBasedLLM().generate(system_prompt, history, user_input)
