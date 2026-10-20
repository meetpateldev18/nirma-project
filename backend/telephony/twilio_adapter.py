"""
Twilio Telephony Adapter Module — Synchronous & Asynchronous Carrier Dispatch.

This module implements the `BaseTelephonyAdapter` interface for Twilio Voice Telephony.
It enables outbound PSTN call dispatch, remote call termination, status polling, and
TwiML-driven voice conversations.

CONCURRENCY & EXECUTION ARCHITECTURE:
    - Synchronous Worker Execution (`place_call_sync`): Used by Celery multiprocessing
      worker tasks (`place_call_task`) to dispatch carrier requests directly. This eliminates
      the performance overhead and thread contention of creating one-off asyncio event loops
      inside synchronous Celery worker processes.
    - Asynchronous Route Execution (`place_call`): For callers operating inside FastAPI's
      asyncio event loop, SDK calls are executed via `asyncio.to_thread()` to prevent
      stalling the ASGI non-blocking I/O event loop.

SANDBOX & LOCAL DEVELOPMENT FALLBACK:
    If Twilio credentials are unconfigured or set to placeholder values, the adapter
    operates in sandbox mode, returning simulated call dispatch results (`mock_tw_...`)
    without incurring carrier charges or failing local development flows.

Dependencies:
    - twilio >= 9.0
    - pydantic >= 2.0
"""

import asyncio
import logging
from typing import Optional
import uuid

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from backend.config import settings
from backend.telephony.adapter import BaseTelephonyAdapter, CallDispatchResult

logger = logging.getLogger(__name__)


class TwilioAdapter(BaseTelephonyAdapter):
    """
    Twilio PSTN provider implementation supporting dual sync/async execution models.

    Attributes:
        account_sid: Twilio Account SID identifier (starts with AC...).
        auth_token: Cryptographic authentication token for Twilio API requests.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> None:
        """
        Initializes the Twilio client wrapper with carrier credentials.

        Args:
            account_sid: Twilio Account SID (defaults to settings.twilio_account_sid).
            auth_token: Twilio Auth Token (defaults to settings.twilio_auth_token).
        """
        self.account_sid = account_sid or settings.twilio_account_sid
        self.auth_token = auth_token or settings.twilio_auth_token
        self._client: Optional[Client] = None

    def _is_mock_mode(self) -> bool:
        """
        Determines whether the adapter should operate in simulated sandbox mode.

        Returns:
            bool: True if credentials are placeholder or absent, False for live dispatch.
        """
        if not self.account_sid or not self.auth_token:
            return True
        sid_lower = self.account_sid.strip().lower()
        token_lower = self.auth_token.strip().lower()
        return (
            sid_lower in ("your_twilio_account_sid", "mock", "none", "")
            or token_lower in ("your_twilio_auth_token", "mock", "none", "")
            or not sid_lower.startswith("ac")
        )

    def _get_client(self) -> Client:
        """
        Lazily initializes and returns the Twilio REST Client instance.

        Returns:
            Client: Initialized Twilio REST Client.
        """
        if self._client is None:
            if self._is_mock_mode():
                logger.warning(
                    "Twilio credentials missing or placeholder. Telephony operating in sandbox mode."
                )
            self._client = Client(self.account_sid, self.auth_token)
        return self._client

    def _sync_create_call(
        self,
        to_number: str,
        answer_url: str,
        hangup_url: str,
        caller_id: str,
    ) -> CallDispatchResult:
        """
        Synchronous wrapper executing Twilio SDK REST call directly.

        Args:
            to_number: Target recipient phone number in E.164 format.
            answer_url: Fully qualified webhook URL triggered when call is answered.
            hangup_url: Fully qualified status callback URL triggered on termination.
            caller_id: Registered Twilio caller ID phone number in E.164 format.

        Returns:
            CallDispatchResult: Carrier Call SID and dispatch status.
        """
        # Sandbox / Mock Fallback for local testing with zero carrier charges
        if self._is_mock_mode():
            mock_sid = f"mock_tw_{uuid.uuid4().hex[:12]}"
            logger.info(
                "MOCK TELEPHONY SANDBOX (Twilio): Simulating call dispatch to %s (SID: %s)",
                to_number,
                mock_sid,
            )
            return CallDispatchResult(call_uuid=mock_sid, status="queued")

        client = self._get_client()
        try:
            logger.info(
                "Twilio REST call -> To: %s, From: %s, Url: %s, StatusCallback: %s",
                to_number,
                caller_id,
                answer_url,
                hangup_url,
            )
            # Twilio Free Trial accounts strictly prohibit 'status_callback_event' and
            # may restrict status callbacks. Attempt dispatch with hangup status callback first,
            # falling back to core parameters (to, from, url) if trial restrictions apply.
            try:
                call_kwargs = {
                    "to": to_number,
                    "from_": caller_id,
                    "url": answer_url,
                }
                if hangup_url:
                    call_kwargs["status_callback"] = hangup_url
                    call_kwargs["status_callback_method"] = "POST"
                call = client.calls.create(**call_kwargs)
            except TwilioRestException as exc:
                exc_str = str(exc).lower()
                if "trial accounts have limited parameter access" in exc_str or "disallowed parameters" in exc_str:
                    logger.warning(
                        "Twilio trial parameter restriction encountered; retrying with core parameters (to, from, url): %s",
                        exc,
                    )
                    call = client.calls.create(
                        to=to_number,
                        from_=caller_id,
                        url=answer_url,
                    )
                else:
                    raise

            call_sid = getattr(call, "sid", "") or ""
            status_val = getattr(call, "status", "queued") or "queued"
            return CallDispatchResult(call_uuid=str(call_sid), status=str(status_val))
        except TwilioRestException as exc:
            logger.error(
                "Twilio REST API error (Code %s): %s",
                getattr(exc, "code", "UNKNOWN"),
                exc.msg if hasattr(exc, "msg") else str(exc),
                exc_info=True,
            )
            return CallDispatchResult(call_uuid="", status="failed", error=str(exc))
        except Exception as exc:
            logger.error("Twilio unexpected call creation failure: %s", exc, exc_info=True)
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
            hangup_url: Hangup/StatusCallback webhook URL.
            caller_id: Registered Twilio caller ID.

        Returns:
            CallDispatchResult: Carrier Call SID and dispatch status.
        """
        return self._sync_create_call(
            to_number=to_number,
            answer_url=answer_url,
            hangup_url=hangup_url,
            caller_id=caller_id,
        )

    async def place_call(
        self,
        to_number: str,
        answer_url: str,
        hangup_url: str,
        caller_id: str,
    ) -> CallDispatchResult:
        """
        Initiates outbound PSTN call asynchronously without blocking the event loop.

        Args:
            to_number: Recipient number in E.164 format.
            answer_url: Answer webhook URL.
            hangup_url: Hangup/StatusCallback webhook URL.
            caller_id: Registered Twilio caller ID.

        Returns:
            CallDispatchResult: Carrier Call SID and dispatch status.
        """
        return await asyncio.to_thread(
            self._sync_create_call,
            to_number,
            answer_url,
            hangup_url,
            caller_id,
        )

    def _sync_hangup_call(self, call_uuid: str) -> bool:
        """
        Synchronous worker executing call termination request to Twilio API.

        Args:
            call_uuid: Twilio Call SID to terminate.

        Returns:
            bool: True if termination succeeded or call was simulated, False on error.
        """
        if call_uuid.startswith("mock_"):
            logger.info("MOCK TELEPHONY SANDBOX (Twilio): Terminating simulated call: %s", call_uuid)
            return True

        client = self._get_client()
        try:
            client.calls(call_uuid).update(status="completed")
            logger.info("Terminated Twilio call SID: %s", call_uuid)
            return True
        except Exception as exc:
            logger.error("Failed to hangup Twilio call SID %s: %s", call_uuid, exc)
            return False

    async def hangup_call(self, call_uuid: str) -> bool:
        """
        Programmatically terminates an active Twilio call asynchronously.

        Args:
            call_uuid: Twilio Call SID.

        Returns:
            bool: True if call termination succeeded, False otherwise.
        """
        return await asyncio.to_thread(self._sync_hangup_call, call_uuid)

    def _sync_transfer_call(self, call_uuid: str, desk_number: str = "+917971606000") -> bool:
        """
        Synchronously transfers an active Twilio call by modifying its live TwiML.

        Args:
            call_uuid: Twilio Call SID.
            desk_number: Recipient desk phone number.

        Returns:
            bool: True if transfer succeeded, False on error.
        """
        if call_uuid.startswith("mock_"):
            logger.info("MOCK TELEPHONY SANDBOX (Twilio): Transferring simulated call %s to %s", call_uuid, desk_number)
            return True

        client = self._get_client()
        try:
            twiml = (
                f'<Response>'
                f'<Say voice="Polly.Aditi" language="en-IN">Transferring your call to the Nirma University Help Desk. Please hold.</Say>'
                f'<Dial>{desk_number}</Dial>'
                f'</Response>'
            )
            client.calls(call_uuid).update(twiml=twiml)
            logger.info("Transferred Twilio call SID %s to desk %s", call_uuid, desk_number)
            return True
        except Exception as exc:
            logger.error("Failed to transfer Twilio call SID %s to %s: %s", call_uuid, desk_number, exc)
            return False

    async def transfer_call(self, call_uuid: str, desk_number: str = "+917971606000") -> bool:
        """
        Transfers an active Twilio call asynchronously without blocking event loop.
        """
        return await asyncio.to_thread(self._sync_transfer_call, call_uuid, desk_number)

    def _sync_get_status(self, call_uuid: str) -> str:
        """
        Synchronous worker querying live call status from Twilio API.

        Args:
            call_uuid: Twilio Call SID.

        Returns:
            str: Carrier status string ('queued', 'ringing', 'in-progress', 'completed', etc.).
        """
        if call_uuid.startswith("mock_"):
            return "in-progress"

        client = self._get_client()
        try:
            call = client.calls(call_uuid).fetch()
            return str(getattr(call, "status", "unknown"))
        except Exception as exc:
            logger.error("Failed to fetch Twilio call status for SID %s: %s", call_uuid, exc)
            return "failed"

    async def get_call_status(self, call_uuid: str) -> str:
        """
        Queries real-time call status asynchronously without blocking event loop.

        Args:
            call_uuid: Twilio Call SID.

        Returns:
            str: Active call status.
        """
        return await asyncio.to_thread(self._sync_get_status, call_uuid)
