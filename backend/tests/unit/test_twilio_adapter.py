"""
Unit Tests — Twilio Telephony Adapter & Carrier Factory.

Tests `backend.telephony.twilio_adapter` and `backend.telephony.factory`:
- Synchronous worker dispatch (`place_call_sync`) in sandbox mode.
- Asynchronous threadpool dispatch (`place_call`) without event-loop blocking.
- Programmatic call termination (`hangup_call`) and status polling (`get_call_status`).
- Live Twilio Client execution with mock SDK calls and exception handling.
- Dynamic factory resolution (`get_telephony_adapter`) between Plivo and Twilio.
- TwiML XML builder generation (`_build_twilio_xml_response`).
"""

from unittest.mock import MagicMock, patch
import pytest

from backend.config import settings
from backend.telephony.factory import get_telephony_adapter
from backend.telephony.plivo_adapter import PlivoAdapter
from backend.telephony.twilio_adapter import TwilioAdapter
from backend.telephony.webhook_handler import _build_twilio_xml_response


def test_twilio_adapter_mock_sync_dispatch():
    """Verifies TwilioAdapter generates simulated SID in sandbox mode for Celery workers."""
    adapter = TwilioAdapter(account_sid="mock", auth_token="mock")
    result = adapter.place_call_sync(
        to_number="+919876543210",
        answer_url="https://calls.nirmauni.ac.in/webhook/twilio/answer?task_id=1",
        hangup_url="https://calls.nirmauni.ac.in/webhook/twilio/hangup?task_id=1",
        caller_id="+15005550006",
    )
    assert result.status == "queued"
    assert result.call_uuid.startswith("mock_tw_")
    assert result.error is None


@pytest.mark.asyncio
async def test_twilio_adapter_mock_async_dispatch():
    """Verifies TwilioAdapter executes asynchronous mock dispatch via threadpool."""
    adapter = TwilioAdapter(account_sid="your_twilio_account_sid", auth_token="your_twilio_auth_token")
    result = await adapter.place_call(
        to_number="+919876543210",
        answer_url="https://calls.nirmauni.ac.in/webhook/twilio/answer?task_id=1",
        hangup_url="https://calls.nirmauni.ac.in/webhook/twilio/hangup?task_id=1",
        caller_id="+15005550006",
    )
    assert result.status == "queued"
    assert result.call_uuid.startswith("mock_tw_")


@pytest.mark.asyncio
async def test_twilio_adapter_mock_hangup_and_status():
    """Verifies hangup_call and get_call_status in mock sandbox mode."""
    adapter = TwilioAdapter(account_sid="mock", auth_token="mock")
    hangup_ok = await adapter.hangup_call("mock_tw_123456")
    assert hangup_ok is True

    status_val = await adapter.get_call_status("mock_tw_123456")
    assert status_val == "in-progress"


def test_twilio_adapter_live_client_success():
    """Verifies TwilioAdapter correctly parses live Twilio API call response."""
    adapter = TwilioAdapter(account_sid="AC11111111111111111111111111111111", auth_token="auth_secret_token_12345")

    mock_call_obj = MagicMock()
    mock_call_obj.sid = "CA1234567890abcdef1234567890abcdef"
    mock_call_obj.status = "queued"

    mock_client = MagicMock()
    mock_client.calls.create.return_value = mock_call_obj

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = adapter.place_call_sync(
            to_number="+919876543210",
            answer_url="https://domain.edu/webhook/twilio/answer?task_id=5",
            hangup_url="https://domain.edu/webhook/twilio/hangup?task_id=5",
            caller_id="+15005550006",
        )
        assert result.call_uuid == "CA1234567890abcdef1234567890abcdef"
        assert result.status == "queued"
        assert result.error is None
        mock_client.calls.create.assert_called_once()


def test_twilio_adapter_trial_account_disallowed_parameters_fallback():
    """Verifies TwilioAdapter automatically retries with core parameters on trial account restrictions."""
    from twilio.base.exceptions import TwilioRestException

    adapter = TwilioAdapter(account_sid="AC11111111111111111111111111111111", auth_token="auth_secret_token_12345")

    mock_client = MagicMock()
    mock_call_obj = MagicMock()
    mock_call_obj.sid = "CA_trial_fallback_sid_12345"
    mock_call_obj.status = "queued"

    # First call raises trial account restricted parameters error; second call succeeds
    trial_error = TwilioRestException(
        status=400,
        uri="/Accounts/Calls.json",
        msg="Invalid or disallowed parameters provided - trial accounts have limited parameter access",
    )
    mock_client.calls.create.side_effect = [trial_error, mock_call_obj]

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = adapter.place_call_sync(
            to_number="+918866241204",
            answer_url="https://domain.edu/webhook/twilio/answer?task_id=1",
            hangup_url="https://domain.edu/webhook/twilio/hangup?task_id=1",
            caller_id="+17372508034",
        )
        assert result.call_uuid == "CA_trial_fallback_sid_12345"
        assert result.status == "queued"
        assert result.error is None
        assert mock_client.calls.create.call_count == 2
        # Check that second call was called with only core parameters (to, from_, url)
        second_call_kwargs = mock_client.calls.create.call_args_list[1].kwargs
        assert second_call_kwargs == {
            "to": "+918866241204",
            "from_": "+17372508034",
            "url": "https://domain.edu/webhook/twilio/answer?task_id=1",
        }


def test_twilio_adapter_live_client_error():
    """Verifies TwilioAdapter catches carrier exceptions and returns failed CallDispatchResult."""
    from twilio.base.exceptions import TwilioRestException

    adapter = TwilioAdapter(account_sid="AC11111111111111111111111111111111", auth_token="auth_secret_token_12345")

    mock_client = MagicMock()
    mock_client.calls.create.side_effect = TwilioRestException(status=400, uri="/Accounts/Calls.json", msg="Invalid phone number")

    with patch.object(adapter, "_get_client", return_value=mock_client):
        result = adapter.place_call_sync(
            to_number="+invalid",
            answer_url="https://domain.edu/answer",
            hangup_url="https://domain.edu/hangup",
            caller_id="+15005550006",
        )
        assert result.call_uuid == ""
        assert result.status == "failed"
        assert "Invalid phone number" in str(result.error)


def test_get_telephony_adapter_factory():
    """Verifies dynamic carrier adapter resolution between Plivo and Twilio."""
    # Explicit Twilio
    tw_adapter = get_telephony_adapter("twilio")
    assert isinstance(tw_adapter, TwilioAdapter)

    # Explicit Plivo
    pl_adapter = get_telephony_adapter("plivo")
    assert isinstance(pl_adapter, PlivoAdapter)

    # Fallback on unknown
    fallback_adapter = get_telephony_adapter("unknown_provider")
    assert isinstance(fallback_adapter, PlivoAdapter)


def test_build_twilio_xml_response():
    """Verifies TwiML generation with <Play> and <Record timeout='2' ...> elements."""
    twiml_str = _build_twilio_xml_response(
        audio_url="https://domain.edu/static/audio/test.wav",
        action_url="https://domain.edu/webhook/twilio/input?task_id=10",
        silence_seconds=2,
    )
    assert "<Response>" in twiml_str
    assert "<Play>https://domain.edu/static/audio/test.wav</Play>" in twiml_str
    assert '<Record action="https://domain.edu/webhook/twilio/input?task_id=10"' in twiml_str
    assert 'timeout="2"' in twiml_str
    assert 'finishOnKey="#"' in twiml_str

    # Hangup XML
    hangup_str = _build_twilio_xml_response(hangup=True)
    assert "<Hangup" in hangup_str


def test_config_carrier_webhook_urls():
    """Verifies dynamic webhook URL construction matching active provider."""
    # When provider is twilio
    with patch.object(settings, "telephony_provider", "twilio"):
        urls = settings.get_carrier_webhook_urls(42)
        assert "/webhook/twilio/answer?task_id=42" in urls["answer_url"]
        assert "/webhook/twilio/hangup?task_id=42" in urls["hangup_url"]

    # When provider is plivo
    with patch.object(settings, "telephony_provider", "plivo"):
        urls = settings.get_carrier_webhook_urls(42)
        assert "/webhook/plivo/answer?task_id=42" in urls["answer_url"]
        assert "/webhook/plivo/hangup?task_id=42" in urls["hangup_url"]
