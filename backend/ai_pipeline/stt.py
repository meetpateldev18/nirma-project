"""
Speech-to-Text (STT) Module — Abstract Adapters, Local Inference & Cloud Failover.

This module provides multilingual speech recognition for English, Hindi, and Gujarati.
It implements the Adapter pattern with automatic circuit-breaking:
- Primary: IndicConformer (0.60B parameters) running locally via NeMo / ONNX / Torch.
- Fallback: Sarvam AI API ('saaras:v4') receiving multipart/form-data audio buffers.

Dependencies:
    - httpx >= 0.27
    - pydantic >= 2.0
"""

import asyncio
import logging
import os
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


def _get_audio_download_auth(audio_url: str) -> Optional[tuple[str, str]]:
    """
    Supplies HTTP Basic Auth credentials for protected carrier endpoints (e.g. Twilio media).

    Twilio recording endpoints enforce HTTP Basic Auth when account media protection
    is enabled. This helper attaches Twilio credentials when fetching from api.twilio.com.
    """
    if "api.twilio.com" in audio_url and settings.twilio_account_sid and settings.twilio_auth_token:
        return (settings.twilio_account_sid, settings.twilio_auth_token)
    return None


class STTAdapter(ABC):
    """
    Abstract interface for Speech-to-Text transcription engines.

    All implementations must be asynchronous and non-blocking.
    """

    @abstractmethod
    async def transcribe(self, audio_url: str, language: str = "hi") -> str:
        """
        Transcribes audio from a remote URL to text.

        Args:
            audio_url: Publicly accessible URL pointing to the recorded audio file.
            language: ISO language code ('hi', 'gu', 'en').

        Returns:
            str: Transcribed text string.

        Raises:
            STTException: If transcription fails after internal retries.
        """
        pass


class IndicConformerSTT(STTAdapter):
    """
    Primary local STT engine utilizing AI4Bharat's IndicConformer 0.60B model.

    Executes speech recognition locally on the server GPU/CPU without transmitting
    student audio data to external third-party cloud services.
    """

    def __init__(self, model_path: Optional[str] = None) -> None:
        """
        Initializes the IndicConformer ASR model.

        Args:
            model_path: Filesystem path to the .nemo model checkpoint.
        """
        self.model_path = model_path or settings.indic_conformer_model_path
        self._model = None
        self._is_loaded = False
        logger.info("Configured IndicConformer STT with model path: %s", self.model_path)

    def _ensure_model_loaded(self) -> None:
        """
        Lazily loads the NeMo ASR model checkpoint into GPU VRAM.

        Guarantees heavy neural network weight loading does not slow down
        application startup.
        """
        if not self._is_loaded:
            try:
                # NeMo collections are imported dynamically to prevent cold-start overhead
                import nemo.collections.asr as nemo_asr
                if os.path.exists(self.model_path):
                    self._model = nemo_asr.models.EncDecCTCModelBPE.restore_from(self.model_path)
                    self._is_loaded = True
                    logger.info("IndicConformer model successfully loaded from %s", self.model_path)
                else:
                    logger.warning(
                        "IndicConformer model path '%s' not found on disk. Primary STT will defer to fallback.",
                        self.model_path,
                    )
            except Exception as exc:
                logger.error("Failed to load IndicConformer model: %s", exc, exc_info=True)
                self._model = None

    def _sync_transcribe(self, temp_audio_path: str) -> str:
        """
        Synchronous model inference executed inside a worker threadpool.

        Args:
            temp_audio_path: Local filesystem path to the downloaded audio file.

        Returns:
            str: Output transcript string.
        """
        self._ensure_model_loaded()
        if self._model is None:
            raise RuntimeError("IndicConformer model is not initialized or model file missing.")
        
        results = self._model.transcribe([temp_audio_path])
        return results[0] if results and len(results) > 0 else ""

    async def transcribe(self, audio_url: str, language: str = "hi") -> str:
        """
        Downloads caller audio and executes local ASR inference asynchronously.

        Args:
            audio_url: Carrier audio recording URL.
            language: Expected language hint.

        Returns:
            str: Normalized speech transcript.

        Raises:
            Exception: If audio downloading or inference fails.
        """
        logger.debug("Downloading audio for local IndicConformer STT: %s", audio_url)
        auth = _get_audio_download_auth(audio_url)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(audio_url, auth=auth)
            resp.raise_for_status()
            audio_bytes = resp.content

        # Write to temporary file for NeMo audio reader
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            # Offload blocking PyTorch computation to threadpool
            transcript = await asyncio.to_thread(self._sync_transcribe, tmp_path)
            return transcript.strip()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class SarvamSTT(STTAdapter):
    """
    Cloud fallback STT engine utilizing the Sarvam AI Speech-to-Text API.

    CRITICAL ARCHITECTURAL STANDARD:
    Sarvam AI requires multipart/form-data with binary audio bytes ('file=@audio.wav')
    and uses the current production 'saaras:v4' model.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        """
        Initializes the Sarvam STT adapter.

        Args:
            api_key: Sarvam AI subscription key from environment.
        """
        self.api_key = api_key if api_key is not None else settings.sarvam_api_key
        self.api_url = "https://api.sarvam.ai/speech-to-text"
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Returns or lazily creates a persistent pooled AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(12.0, connect=3.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            )
        return self._client

    async def aclose(self) -> None:
        """Gracefully closes persistent HTTP connection pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _map_language_code(self, lang: str) -> str:
        """
        Maps standard ISO 639-1 language code to Sarvam BCP-47 language code.

        Args:
            lang: Language string ('hi', 'gu', 'en').

        Returns:
            str: BCP-47 language tag (e.g., 'hi-IN').
        """
        mapping = {
            "hi": "hi-IN",
            "gu": "gu-IN",
            "en": "en-IN",
        }
        return mapping.get(lang.lower(), "hi-IN")

    async def transcribe(self, audio_url: str, language: str = "hi") -> str:
        """
        Downloads caller audio and submits multipart/form-data to Sarvam AI API.

        Args:
            audio_url: Audio recording URL.
            language: Target Indian language ISO code.

        Returns:
            str: High-accuracy cloud transcript.

        Raises:
            ValueError: If SARVAM_API_KEY is not configured.
            httpx.HTTPError: If API request fails.
        """
        if not self.api_key:
            raise ValueError("SARVAM_API_KEY environment variable is not configured.")

        client = await self._get_client()

        # Step 1: Download audio buffer from carrier using pooled connection
        auth = _get_audio_download_auth(audio_url)
        audio_resp = await client.get(audio_url, auth=auth)
        audio_resp.raise_for_status()
        audio_bytes = audio_resp.content

        # Step 2: Dispatch binary audio to Sarvam AI
        files = {"file": ("caller_audio.wav", audio_bytes, "audio/wav")}
        data = {
            "model": "saaras:v4",
            "mode": "transcribe",
            "language_code": self._map_language_code(language),
            "with_diarization": "false",
        }
        headers = {"api-subscription-key": self.api_key}

        resp = await client.post(self.api_url, headers=headers, files=files, data=data)
        resp.raise_for_status()
        result = resp.json()
        return result.get("transcript", "").strip()


class FallbackSTT(STTAdapter):
    """
    Resilient composite STT adapter implementing latency-bounded failover.

    Attempts primary local inference with an explicit timeout. If the primary
    engine fails, times out, or lacks model weights, it automatically degrades
    to the cloud fallback provider.
    """

    def __init__(
        self,
        primary: Optional[STTAdapter] = None,
        fallback: Optional[STTAdapter] = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        """
        Initializes the FallbackSTT composite.

        Args:
            primary: Primary local ASR adapter (default: IndicConformerSTT).
            fallback: Secondary cloud ASR adapter (default: SarvamSTT).
            timeout_seconds: Strict latency deadline for the primary engine (default: 2.0s).
        """
        self.primary = primary or IndicConformerSTT()
        self.fallback = fallback or SarvamSTT()
        self.timeout_seconds = timeout_seconds

    async def transcribe(self, audio_url: str, language: str = "hi") -> str:
        """
        Executes bounded transcription with automatic failover.

        Args:
            audio_url: Audio recording URL.
            language: Target language code.

        Returns:
            str: Speech transcript.
        """
        t0 = time.monotonic()
        try:
            logger.info("Attempting primary local STT (timeout=%.1fs)...", self.timeout_seconds)
            transcript = await asyncio.wait_for(
                self.primary.transcribe(audio_url, language),
                timeout=self.timeout_seconds,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.info("Primary STT completed in %d ms: '%s'", elapsed_ms, transcript)
            return transcript
        except (asyncio.TimeoutError, Exception) as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(
                "Primary STT failed or exceeded timeout (%d ms) with error '%s'. Triggering Sarvam AI fallback...",
                elapsed_ms,
                exc,
            )
            t_fallback = time.monotonic()
            transcript = await self.fallback.transcribe(audio_url, language)
            fallback_ms = int((time.monotonic() - t_fallback) * 1000)
            logger.info("Fallback STT completed in %d ms: '%s'", fallback_ms, transcript)
            return transcript
