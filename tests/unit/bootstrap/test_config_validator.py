"""Unit tests for bootstrap ConfigurationValidator."""

from __future__ import annotations

import pytest

from dfat.bootstrap.config_validator import ConfigurationValidator
from dfat.bootstrap.models import InitPhase, InitStatus
from dfat.settings import DFATSettings, load_settings


def _settings(**overrides: object) -> DFATSettings:
    base = load_settings(env="development")
    data = base.model_dump()
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    return DFATSettings(**data)


@pytest.mark.asyncio
async def test_passes_with_valid_development_config() -> None:
    validator = ConfigurationValidator()
    result = await validator.validate(load_settings(env="development"))
    assert result.phase == InitPhase.CONFIGURATION
    assert result.status == InitStatus.COMPLETED
    assert result.is_critical is True
    assert result.error is None
    assert "passed" in result.message.lower() or "passed" in str(result.details)


@pytest.mark.asyncio
async def test_catches_missing_short_jwt_secret() -> None:
    settings = _settings(auth={"secret_key": "short"})
    result = await ConfigurationValidator().validate(settings)
    assert result.status == InitStatus.FAILED
    assert result.error is not None
    assert "JWT" in result.error or "jwt" in result.error.lower()
    assert "32" in result.error


@pytest.mark.asyncio
async def test_catches_jwt_placeholder_in_production() -> None:
    settings = _settings(
        env="production",
        auth={"secret_key": "CHANGE-ME-IN-PRODUCTION-USE-SECRETS"},
        evidence={"evidence_dir": "/var/lib/dfat/evidence"},
        reporting={"output_dir": "/var/lib/dfat/reports"},
        logging={"audit_log_path": "/var/log/dfat/audit.log"},
    )
    result = await ConfigurationValidator().validate(settings)
    assert result.status == InitStatus.FAILED
    assert result.error is not None
    assert "placeholder" in result.error.lower()


@pytest.mark.asyncio
async def test_catches_external_llm_url() -> None:
    settings = _settings(
        ai_engine={"llm_api_url": "https://api.openai.com/v1/chat/completions"}
    )
    result = await ConfigurationValidator().validate(settings)
    assert result.status == InitStatus.FAILED
    assert result.error is not None
    assert "Non-local" in result.error or "localhost" in result.error.lower()
    assert "Remediation" in result.error or "DFAT_AI_ENGINE" in result.error


@pytest.mark.asyncio
async def test_catches_invalid_database_url() -> None:
    settings = _settings(database={"url": "not-a-valid-url"})
    result = await ConfigurationValidator().validate(settings)
    assert result.status == InitStatus.FAILED
    assert result.error is not None
    assert "Database" in result.error or "database" in result.error.lower()


@pytest.mark.asyncio
async def test_messages_are_actionable_on_failure() -> None:
    settings = _settings(
        auth={"secret_key": "x"},
        ai_engine={"llm_api_url": "http://evil.example/llm", "llm_model": ""},
        database={"url": ""},
    )
    result = await ConfigurationValidator().validate(settings)
    assert result.status == InitStatus.FAILED
    assert result.error is not None
    assert "Set " in result.error or "DFAT_" in result.error
