from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Conversation, ConversationMessage, UserProfile


MAX_CONVERSATIONS = 80
MAX_MESSAGES = 120


async def list_conversations(session: AsyncSession, profile: UserProfile) -> dict[str, Any]:
    conversations = (
        await session.execute(
            select(Conversation)
            .where(Conversation.user_id == profile.id)
            .order_by(desc(Conversation.is_active), desc(Conversation.updated_at))
            .limit(MAX_CONVERSATIONS)
        )
    ).scalars().all()
    active = next((item for item in conversations if item.is_active), None)
    return {
        "conversations": [await serialize_conversation(session, item) for item in conversations],
        "activeConversationId": active.client_id if active else conversations[0].client_id if conversations else "",
    }


async def sync_conversations(session: AsyncSession, profile: UserProfile, payload) -> dict[str, Any]:
    await session.execute(update(Conversation).where(Conversation.user_id == profile.id).values(is_active=0))
    seen_client_ids: set[str] = set()
    active_client_id = str(payload.activeConversationId or "").strip()

    for raw in payload.conversations[:MAX_CONVERSATIONS]:
        client_id = normalize_client_id(raw.id)
        if not client_id or client_id in seen_client_ids:
            continue
        seen_client_ids.add(client_id)
        conversation = await upsert_conversation(session, profile.id, client_id, raw.title, client_id == active_client_id)
        await session.flush()
        await replace_messages(session, profile.id, conversation.id, raw.messages[-MAX_MESSAGES:])

    if active_client_id and active_client_id not in seen_client_ids and seen_client_ids:
        first = next(iter(seen_client_ids))
        await session.execute(
            update(Conversation)
            .where(Conversation.user_id == profile.id, Conversation.client_id == first)
            .values(is_active=1)
        )
    await session.flush()
    return await list_conversations(session, profile)


async def delete_conversation(session: AsyncSession, profile: UserProfile, client_id: str) -> bool:
    conversation = (
        await session.execute(
            select(Conversation)
            .where(Conversation.user_id == profile.id, Conversation.client_id == normalize_client_id(client_id))
            .limit(1)
        )
    ).scalar_one_or_none()
    if not conversation:
        return False
    await session.execute(delete(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id))
    await session.delete(conversation)
    await session.flush()
    return True


async def upsert_conversation(session: AsyncSession, user_id: str, client_id: str, title: str, active: bool) -> Conversation:
    conversation = (
        await session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.client_id == client_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if not conversation:
        conversation = Conversation(user_id=user_id, client_id=client_id)
        session.add(conversation)
    conversation.title = normalize_title(title)
    conversation.is_active = 1 if active else 0
    conversation.updated_at = datetime.utcnow()
    return conversation


async def replace_messages(session: AsyncSession, user_id: str, conversation_id: str, messages: list) -> None:
    await session.execute(delete(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id))
    for index, raw in enumerate(messages):
        role = str(getattr(raw, "role", "") or "").strip()
        if role not in {"peach", "user", "system"}:
            continue
        content = str(getattr(raw, "content", "") or "").strip()
        if not content:
            continue
        session.add(
            ConversationMessage(
                user_id=user_id,
                conversation_id=conversation_id,
                role=role,
                content=content[:8000],
                actions=normalize_actions(getattr(raw, "actions", [])),
                sort_order=index,
            )
        )


async def serialize_conversation(session: AsyncSession, conversation: Conversation) -> dict[str, Any]:
    messages = (
        await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.sort_order, ConversationMessage.created_at)
            .limit(MAX_MESSAGES)
        )
    ).scalars().all()
    return {
        "id": conversation.client_id,
        "server_id": conversation.id,
        "title": conversation.title,
        "updatedAt": "刚刚",
        "messages": [
            {
                "role": item.role,
                "content": item.content,
                "actions": item.actions or [],
            }
            for item in messages
        ],
    }


def normalize_client_id(value: str) -> str:
    clean = "".join(ch for ch in str(value or "").strip() if ch.isalnum() or ch in "-_:")
    return clean[:80]


def normalize_title(value: str) -> str:
    clean = " ".join(str(value or "新建对话").split())
    return (clean or "新建对话")[:120]


def normalize_actions(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value[:8] if isinstance(item, dict)]
