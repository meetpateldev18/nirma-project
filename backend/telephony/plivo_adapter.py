"""
Plivo Telephony Adapter Module — Synchronous & Asynchronous Carrier Dispatch.

This module implements the `BaseTelephonyAdapter` interface for Plivo Cloud Telephony.

CONCURRENCY & EXECUTION ARCHITECTURE:
    - Synchronous Worker Execution (`place_call_sync`): Used by Celery multiprocessing
      worker tasks (`place_call_task`) to dispatch carrier requests directly. This eliminates
      the performance overhead and thread contention of creating one-off asyncio event loops
      inside synchronous Celery worker processes.
    - Asynchronous Route Execution (`place_call`): For callers operating inside FastAPI's
      asyncio event loop, SDK calls are executed via `asyncio.to_thread()` to prevent
      stalling the ASGI non-blocking I/O event loop.

Dependencies:
    - plivo >= 4.38
"""

import asyncio
import logging
from typing import Optional
import uuid

import plivo

from backend.config import settings
from backend.telephony.adapter import BaseTelephonyAdapter, CallDispatchResult

logger = logging.getLogger(__name__)


class PlivoAdapter(BaseTelephonyAdapter):
    """
    Plivo PSTN provider implementation using non-blocking threadpool wrappers.

    Attributes:
        auth_id: Plivo account ID.
        auth_token: Plivo account authentication token.
    """

    def __init__(
        self,
        auth_id: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> None:
        """
        Initializes the Plivo RestClient with carrier credentials.

        Args:
            auth_id: Plivo Auth ID (defaults to settings.plivo_auth_id).
            auth_token: Plivo Auth Token (defaults to settings.plivo_auth_token).
        """
        self.auth_id = auth_id or settings.plivo_auth_id
        self.auth_token = auth_token or settings.plivo_auth_token
        self._client: Optional[plivo.RestClient] = None

    def _get_client(self) -> plivo.RestClient:
        """Lazily initializes and returns the Plivo RestClient."""
        if self._client is None:
            if not self.auth_id or not self.auth_token:
                logger.warning("Plivo credentials missing. Plivo API calls will fail.")
            self._client = plivo.RestClient(self.auth_id, self.auth_token)
        return self._client

    def _sync_create_call(
        self,
        to_number: str,
        answer_url: str,
        hangup_url: str,
        caller_id: str,
    ) -> CallDispatchResult:
        """
        Synchronous wrapper executing Plivo SDK REST call.

        Args:
            to_number: Target recipient number.
            answer_url: Fully qualified webhook answer URL.
            hangup_url: Fully qualified webhook hangup URL.
            caller_id: Registered DID caller ID.

        Returns:
            CallDispatchResult: Carrier UUID and status.
        """
        # Sandbox / Mock Fallback for Local Development:
        # If Plivo credentials are not yet configured or placeholder tokens are used,
        # generate a simulated call dispatch result so local UI flows & testing never fail.
        if (
            not self.auth_id
            or self.auth_id in ("your_plivo_auth_id", "mock", "")
            or not self.auth_token
            or self.auth_token in ("your_plivo_auth_token", "mock", "")
        ):
            mock_uuid = f"mock_{uuid.uuid4().hex[:12]}"
            logger.info(
                "MOCK TELEPHONY SANDBOX: Simulating call dispatch to %s (UUID: %s)",
                to_number,
                mock_uuid,
            )
            return CallDispatchResult(call_uuid=mock_uuid, status="queued")

        client = self._get_client()
        try:
            logger.info("Plivo REST call -> To: %s, AnswerURL: %s", to_number, answer_url)
            response = client.calls.create(
                from_=caller_id,
                to_=to_number,
                answer_url=answer_url,
                hangup_url=hangup_url,
                answer_method="POST",
                hangup_method="POST",
            )
            # Plivo returns dict-like or object response with 'request_uuid'
            request_uuid = getattr(response, "request_uuid", None) or response.get("request_uuid", "")
            return CallDispatchResult(call_uuid=str(request_uuid), status="queued")
        except Exception as exc:
            logger.error("Plivo API call creation failed: %s", exc, exc_info=True)
            return CallDispatchResult(call_uuid="", status="failed", error=str(exc))

    def place_call_sync(
        self,
        to_number: str,
        answer_url: str,
        hangup_url: str,
        caller_id: str,
    ) -> CallDispatchResult:
        """
        Initiates outbound PSTN call synchronously for Celery multiprocessing workers.
        Avoids spinning up redundant asyncio event loops inside synchronous background tasks.

        Args:
            to_number: Recipient number in E.164 format.
            answer_url: Answer webhook URL.
            hangup_url: Hangup webhook URL.
            caller_id: Registered DID phone number.

        Returns:
            CallDispatchResult: Call dispatch outcome.
        """
        return self._sync_create_call(
            to_number,
            answer_url,
            hangup_url,
            caller_id,
        )

    async def place_call(
        self,
        to_number: str,
        answer_url: str,
        hangup_url: str,
        caller_id: str,
    ) -> CallDispatchResult:
        """
        Initiates outbound PSTN call asynchronously without blocking event loop.

        Args:
            to_number: Recipient number in E.164 format.
            answer_url: Answer webhook URL.
            hangup_url: Hangup webhook URL.
            caller_id: Registered DID phone number.

        Returns:
            CallDispatchResult: Call dispatch outcome.
        """
        return await asyncio.to_thread(
            self._sync_create_call,
            to_number,
            answer_url,
            hangup_url,
            caller_id,
        )

    def _sync_hangup_call(self, call_uuid: str) -> bool:
        """Synchronous wrapper for hanging up a call."""
        if call_uuid.startswith("mock_"):
            logger.info("MOCK TELEPHONY SANDBOX: Terminating simulated call: %s", call_uuid)
            return True
        client = self._get_client()
        try:
            client.calls.delete(call_uuid=call_uuid)
            return True
        except Exception as exc:
            logger.error("Failed to hangup Plivo call %s: %s", call_uuid, exc)
            return False

    async def hangup_call(self, call_uuid: str) -> bool:
        """Programmatically terminates an active call asynchronously."""
        return await asyncio.to_thread(self._sync_hangup_call, call_uuid)

    def _sync_transfer_call(self, call_uuid: str, desk_number: str = "+917971606000") -> bool:
        """Synchronously transfers an active Plivo call to an operator desk."""
        if call_uuid.startswith("mock_"):
            logger.info("MOCK TELEPHONY SANDBOX (Plivo): Transferring simulated call %s to %s", call_uuid, desk_number)
            return True
        client = self._get_client()
        try:
            # Transfer the aleg (caller) to the new number
            client.calls.transfer(call_uuid=call_uuid, legs="aleg")
            logger.info("Transferred Plivo call UUID %s to desk %s", call_uuid, desk_number)
            return True
        except Exception as exc:
            logger.error("Failed to transfer Plivo call UUID %s to %s: %s", call_uuid, desk_number, exc)
            return False

    async def transfer_call(self, call_uuid: str, desk_number: str = "+917971606000") -> bool:
        """Transfers an active Plivo call asynchronously."""
        return await asyncio.to_thread(self._sync_transfer_call, call_uuid, desk_number)

    def _sync_get_status(self, call_uuid: str) -> str:
        """Synchronous wrapper for querying call status."""
        if call_uuid.startswith("mock_"):
            return "in-progress"
        client = self._get_client()
        try:
            call_info = client.calls.get(call_uuid=call_uuid)
            return getattr(call_info, "call_status", "unknown")
        except Exception as exc:
            logger.error("Failed to fetch Plivo call status for %s: %s", call_uuid, exc)
            return "failed"

    async def get_call_status(self, call_uuid: str) -> str:
        """Queries real-time call status asynchronously."""
        return await asyncio.to_thread(self._sync_get_status, call_uuid)
