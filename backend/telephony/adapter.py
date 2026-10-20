"""
Telephony Adapter Module — Abstract Interface & Carrier Provider Contracts.

This module decouples external PSTN telephony vendor details (Plivo, Asterisk, Twilio)
from the core business workflow and call state machine using the Adapter pattern.

Design Invariants:
    - All implementations must be non-blocking and safe for asynchronous frameworks.
    - Vendor-specific credentials and SDK calls are isolated behind this interface.

Dependencies:
    - pydantic >= 2.0
"""

from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel, Field


class CallDispatchResult(BaseModel):
    """
    Data transfer object representing the immediate result of an outbound call dispatch.

    Attributes:
        call_uuid: Unique request or call identifier assigned by the carrier API.
        status: Carrier dispatch status ('queued', 'ringing', 'failed').
        error: Diagnostic error message if carrier request failed, otherwise None.
    """

    call_uuid: str = Field(..., description="Unique carrier identifier")
    status: str = Field(..., description="Immediate call dispatch status")
    error: Optional[str] = Field(None, description="Diagnostic error details if failed")


class BaseTelephonyAdapter(ABC):
    """
    Abstract base interface for all telephony service provider adapters.

    Concrete implementations must translate vendor-specific REST API calls
    and XML schema dialects into standard internal datatypes.
    """

    @abstractmethod
    async def place_call(
        self,
        to_number: str,
        answer_url: str,
        hangup_url: str,
        caller_id: str,
    ) -> CallDispatchResult:
        """
        Initiates an outbound PSTN call to the target phone number.

        Args:
            to_number: Recipient phone number in E.164 format (e.g. '+919876543210').
            answer_url: Fully qualified HTTPS webhook URL triggered when call is answered.
            hangup_url: Fully qualified HTTPS webhook URL triggered upon call disconnection.
            caller_id: Registered DID phone number matching carrier account credentials.

        Returns:
            CallDispatchResult: Carrier UUID and initial dispatch status.

        Raises:
            TelephonyCarrierException: If network or carrier authentication fails.
        """
        pass

    def place_call_sync(
        self,
        to_number: str,
        answer_url: str,
        hangup_url: str,
        caller_id: str,
    ) -> CallDispatchResult:
        """
        Initiates an outbound PSTN call synchronously.

        Designed specifically for Celery background multiprocessing worker tasks to
        dispatch calls directly to the carrier REST API without the latency overhead
        and thread thrashing of instantiating one-off asyncio event loops.

        Args:
            to_number: Recipient phone number in E.164 format (e.g. '+919876543210').
            answer_url: Fully qualified HTTPS webhook URL triggered when call is answered.
            hangup_url: Fully qualified HTTPS webhook URL triggered upon call disconnection.
            caller_id: Registered DID phone number matching carrier account credentials.

        Returns:
            CallDispatchResult: Carrier UUID and initial dispatch status.

        Raises:
            TelephonyCarrierException: If network or carrier authentication fails.
        """
        raise NotImplementedError("Synchronous call placement not implemented for this adapter.")

    @abstractmethod
    async def hangup_call(self, call_uuid: str) -> bool:
        """
        Programmatically terminates an active phone call.

        Args:
            call_uuid: Carrier call identifier.

        Returns:
            bool: True if termination request succeeded, False otherwise.
        """
        pass

    async def transfer_call(self, call_uuid: str, desk_number: str = "+917971606000") -> bool:
        """
        Transfers an active telephone call to a destination department or help desk phone number.

        Args:
            call_uuid: Carrier call identifier.
            desk_number: Destination phone number in E.164 format.

        Returns:
            bool: True if transfer initiated successfully, False otherwise.
        """
        raise NotImplementedError("Call transfer not supported by this adapter.")

    @abstractmethod
    async def get_call_status(self, call_uuid: str) -> str:
        """
        Queries carrier for real-time status of a call.

        Args:
            call_uuid: Carrier call identifier.

        Returns:
            str: Carrier call state string.
        """
        pass
