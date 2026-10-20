"""
Telephony Adapter Factory Module — Dynamic PSTN Carrier Resolution.

This module provides factory resolution of concrete telephony adapters based on
application configuration. It enables dynamic switching between:
- 'plivo': Primary carrier for Indian domestic PSTN routing and DLT compliance.
- 'twilio': Secondary/alternative carrier offering global reach and free developer trial sandbox.

Dependencies:
    - backend.config.settings
    - backend.telephony.adapter.BaseTelephonyAdapter
"""

import logging
from typing import Optional

from backend.config import settings
from backend.telephony.adapter import BaseTelephonyAdapter
from backend.telephony.plivo_adapter import PlivoAdapter
from backend.telephony.twilio_adapter import TwilioAdapter

logger = logging.getLogger(__name__)


def get_telephony_adapter(provider: Optional[str] = None) -> BaseTelephonyAdapter:
    """
    Factory resolving the active concrete telephony adapter based on runtime configuration.

    Args:
        provider: Optional explicit carrier string ('plivo' or 'twilio').
                  If omitted, defaults to settings.telephony_provider.

    Returns:
        BaseTelephonyAdapter: Configured concrete provider adapter instance.
    """
    target = (provider or settings.telephony_provider or "plivo").strip().lower()

    if target == "twilio":
        logger.debug(
            "Resolving Twilio telephony adapter (Account SID: %s...)",
            settings.twilio_account_sid[:8] if settings.twilio_account_sid else "None",
        )
        return TwilioAdapter(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
        )

    if target != "plivo":
        logger.warning(
            "Unrecognized telephony provider '%s'. Falling back to Plivo as default carrier.",
            target,
        )

    logger.debug(
        "Resolving Plivo telephony adapter (Auth ID: %s...)",
        settings.plivo_auth_id[:8] if settings.plivo_auth_id else "None",
    )
    return PlivoAdapter(
        auth_id=settings.plivo_auth_id,
        auth_token=settings.plivo_auth_token,
    )
