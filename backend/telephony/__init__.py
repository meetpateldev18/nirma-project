"""
Telephony Subpackage Exports — Multi-Carrier Abstraction & Factory.
"""

from backend.telephony.adapter import BaseTelephonyAdapter, CallDispatchResult
from backend.telephony.factory import get_telephony_adapter
from backend.telephony.plivo_adapter import PlivoAdapter
from backend.telephony.twilio_adapter import TwilioAdapter

__all__ = [
    "BaseTelephonyAdapter",
    "CallDispatchResult",
    "PlivoAdapter",
    "TwilioAdapter",
    "get_telephony_adapter",
]
