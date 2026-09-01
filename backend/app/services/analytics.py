from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import ProductEvent, UserProfile


SENSITIVE_KEYS = {
    "password",
    "phone",
    "email",
    "id_card",
    "resume",
    "resume_text",
    "full_resume",
    "chat",
    "message",
    "answer",
    "transcript",
    "emotion_raw",
    "token",
    "api_key",
    "secret",
}
SENSITIVE_PATTERNS = [
    re.compile(r"1[3-9]\d{9}"),
    re.compile(r"1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\d{15,18}[xX]?\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
]


async def record_product_event(session: AsyncSession, profile: UserProfile, payload) -> ProductEvent:
    event = ProductEvent(
        user_id=profile.id,
        anonymous_id=short_value(payload.anonymous_id, 80),
        session_id=short_value(payload.session_id, 80),
        event_name=normalize_event_name(payload.event_name),
        page=short_value(payload.page, 80),
        module=short_value(payload.module, 80),
        source=short_value(payload.source, 120),
        properties=sanitize_properties(payload.properties),
        client_version=short_value(payload.client_version, 60),
        device_type=short_value(payload.device_type, 40),
        browser=short_value(payload.browser, 80),
        referrer=short_value(payload.referrer, 500),
    )
    session.add(event)
    await session.flush()
    return event


async def analytics_summary(session: AsyncSession, user_id: str | None = None) -> dict[str, Any]:
    query = select(ProductEvent.event_name, func.count(ProductEvent.id)).group_by(ProductEvent.event_name)
    if user_id:
        query = query.where(ProductEvent.user_id == user_id)
    rows = (await session.execute(query)).all()
    total_query = select(func.count(ProductEvent.id))
    if user_id:
        total_query = total_query.where(ProductEvent.user_id == user_id)
    return {
        "total_events": int(await session.scalar(total_query) or 0),
        "events": {str(name): int(count) for name, count in rows},
    }


def normalize_event_name(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(value or "").strip())[:120]
    return clean or "unknown_event"


def sanitize_properties(value: Any, depth: int = 0) -> dict[str, Any]:
    if not isinstance(value, dict) or depth > 2:
        return {}
    sanitized: dict[str, Any] = {}
    for key, raw in value.items():
        key_text = short_value(str(key), 80)
        if key_is_sensitive(key_text):
            sanitized[key_text] = "[redacted]"
            continue
        sanitized[key_text] = sanitize_value(raw, depth + 1)
        if len(sanitized) >= 40:
            break
    return sanitized


def sanitize_value(value: Any, depth: int) -> Any:
    if isinstance(value, dict):
        return sanitize_properties(value, depth)
    if isinstance(value, list):
        return [sanitize_value(item, depth + 1) for item in value[:20]]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return value
    return scrub_text(str(value))[:240]


def key_is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in SENSITIVE_KEYS)


def scrub_text(value: str) -> str:
    clean = re.sub(r"\s+", " ", value).strip()
    for pattern in SENSITIVE_PATTERNS:
        clean = pattern.sub("[redacted]", clean)
    return clean


def short_value(value: str, limit: int) -> str:
    return scrub_text(str(value or ""))[:limit]
