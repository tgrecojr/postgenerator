"""Effective configuration for the Settings page, with secrets masked, plus a key check."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from postgen.config import Settings
from postgen.llm import LLM

SECRET_FIELDS = frozenset({"anthropic_api_key", "tavily_api_key"})


@dataclass
class SettingRow:
    env: str
    value: str
    secret: bool


def mask(value: str | None) -> str:
    if not value:
        return "missing"
    return f"set (…{value[-4:]})" if len(value) > 8 else "set"


def _env_name(field: str, info: Any) -> str:
    return str(info.alias) if info.alias else f"POSTGEN_{field.upper()}"


def effective_settings(settings: Settings) -> list[SettingRow]:
    rows: list[SettingRow] = []
    for field, info in Settings.model_fields.items():
        raw = getattr(settings, field)
        secret = field in SECRET_FIELDS
        if secret:
            value = mask(raw)
        elif raw is None:
            value = "(default)"
        else:
            value = str(raw)
        rows.append(SettingRow(_env_name(field, info), value, secret))
    return rows


def test_connection(settings: Settings, llm: LLM | None = None) -> tuple[bool, str]:
    """Make one cheap API call to prove the key and default model are usable."""
    try:
        name = (llm or LLM(settings)).ping()
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, f"OK: {settings.model} ({name}) is reachable with this key"
