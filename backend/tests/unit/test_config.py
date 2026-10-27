"""
Unit Tests — Configuration, Environment Variables & Networking Invariants.

Tests the `Settings` class in `backend.config` to verify Twelve-Factor App compliance,
URL construction, institutional domain binding, CORS parsing, and security parameters.
"""

import os
import pytest
from backend.config import Settings


def test_default_settings_instantiation():
    """Verifies that default settings load with expected non-empty institutional defaults."""
    config = Settings()
    assert config.app_name == "Nirma Calling Assistant"
    assert config.base_url.startswith("http")
    assert not config.base_url.endswith("/")
    assert config.jwt_algorithm == "HS256"
    assert config.access_token_expire_minutes > 0
    assert config.refresh_token_expire_days > 0


def test_base_url_trailing_slash_normalization():
    """Verifies that trailing slashes are stripped from base_url to ensure clean URL building."""
    config = Settings(base_url="https://calls.nirmauni.ac.in/")
    assert config.base_url == "https://calls.nirmauni.ac.in"


def test_build_webhook_url_formatting():
    """Verifies dynamic webhook URL construction with both leading and non-leading slashes."""
    config = Settings(base_url="https://calls.nirmauni.ac.in")

    # With leading slash
    url1 = config.build_webhook_url("/webhook/plivo/answer")
    assert url1 == "https://calls.nirmauni.ac.in/webhook/plivo/answer"

    # Without leading slash
    url2 = config.build_webhook_url("webhook/plivo/hangup?task_id=42")
    assert url2 == "https://calls.nirmauni.ac.in/webhook/plivo/hangup?task_id=42"


def test_cors_origins_parsing():
    """Verifies that comma-separated origins are parsed and sanitized into a list."""
    config = Settings(
        allowed_origins="http://localhost:3000, https://calls.nirmauni.ac.in , http://localhost:5173"
    )
    origins = config.cors_origins
    assert len(origins) == 3
    assert "http://localhost:3000" in origins
    assert "https://calls.nirmauni.ac.in" in origins
    assert "http://localhost:5173" in origins


def test_cors_origins_empty_string():
    """Verifies that an empty allowed_origins string returns an empty list without whitespace elements."""
    config = Settings(allowed_origins=" , ")
    assert config.cors_origins == []


def test_audio_cache_dir_fallback():
    """Verifies that audio_cache_dir is a valid non-empty path."""
    config = Settings()
    assert config.audio_cache_dir
    assert isinstance(config.audio_cache_dir, str)
