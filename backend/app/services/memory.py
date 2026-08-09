import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import AgentMemory, UserProfile
from backend.app.services.agent import PeachAgent


MEMORY_LIMIT = 5
MAX_USER_MEMORIES = 80
MEMORY_KIND_LABELS = {
    "profile_fact": "用户事实",
    "preference": "沟通偏好",
    "job_goal": "求职目标",
    "skill_signal": "能力信号",
    "weakness": "薄弱点",
    "interview_pattern": "面试模式",
    "episodic_summary": "阶段总结",
}


async def retrieve_relevant_memories(
    session: AsyncSession,
    user_id: str,
    query: str,
    limit: int = MEMORY_LIMIT,
) -> list[AgentMemory]:
    memories = (
        await session.execute(
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .order_by(desc(AgentMemory.updated_at))
            .limit(120)
        )
    ).scalars().all()
    if not memories:
        return []

    query_terms = tokenize(query)
    scored = sorted(
        memories,
        key=lambda memory: memory_score(memory, query_terms),
        reverse=True,
    )
    selected = [memory for memory in scored if memory_score(memory, query_terms) > 0][:limit]
    if not selected:
        selected = scored[: min(limit, 3)]

    now = datetime.now(timezone.utc)
    for memory in selected:
        memory.use_count = (memory.use_count or 0) + 1
        memory.last_used_at = now
    return selected


def build_memory_context(memories: list[AgentMemory]) -> str:
    if not memories:
        return "暂无可用长期记忆。"
    lines = []
    for memory in memories[:MEMORY_LIMIT]:
        label = MEMORY_KIND_LABELS.get(memory.kind, memory.kind or "记忆")
        tags = "、".join(memory.tags or [])
        suffix = f"（{tags}）" if tags else ""
        lines.append(f"- [{label}] {memory.content}{suffix}")
    return "\n".join(lines)[:1200]


async def remember_interaction(
    session: AsyncSession,
    agent: PeachAgent,
    profile: UserProfile,
    source: str,
    user_message: str,
    assistant_reply: str = "",
    context: dict[str, Any] | None = None,
) -> list[AgentMemory]:
    if not should_consider_memory(user_message, assistant_reply):
        return []
    candidates = await agent.extract_memories(
        profile,
        source=source,
        user_message=user_message,
        assistant_reply=assistant_reply,
        context=context or {},
    )
    saved: list[AgentMemory] = []
    for candidate in candidates[:4]:
        content = str(candidate.get("content") or "").strip()
        if not is_valid_memory_content(content):
            continue
        memory = await upsert_memory(session, profile.id, {
            "kind": normalize_kind(str(candidate.get("kind") or "semantic")),
            "content": content,
            "source": source,
            "confidence": int(candidate.get("confidence") or 70),
            "tags": normalize_tags(candidate.get("tags")),
            "memory_metadata": {
                "reason": str(candidate.get("reason") or "")[:240],
                "extracted_from": source,
            },
        })
        saved.append(memory)
    if saved:
        await trim_memories(session, profile.id)
    return saved


async def upsert_memory(session: AsyncSession, user_id: str, data: dict[str, Any]) -> AgentMemory:
    content = str(data["content"]).strip()
    existing = await find_similar_memory(session, user_id, content, str(data.get("kind") or "semantic"))
    if existing:
        existing.content = merge_memory_text(existing.content, content)
        existing.source = str(data.get("source") or existing.source)
        existing.confidence = max(int(existing.confidence or 0), int(data.get("confidence") or 70))
        existing.tags = merge_lists(existing.tags or [], data.get("tags") or [])
        existing.memory_metadata = {**(existing.memory_metadata or {}), **(data.get("memory_metadata") or {})}
        return existing

    memory = AgentMemory(
        user_id=user_id,
        kind=str(data.get("kind") or "semantic"),
        content=content,
        source=str(data.get("source") or "chat"),
        confidence=max(0, min(100, int(data.get("confidence") or 70))),
        tags=normalize_tags(data.get("tags")),
        memory_metadata=data.get("memory_metadata") or {},
    )
    session.add(memory)
    return memory


async def find_similar_memory(session: AsyncSession, user_id: str, content: str, kind: str) -> AgentMemory | None:
    content_terms = tokenize(content)
    if not content_terms:
        return None
    memories = (
        await session.execute(
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .where(AgentMemory.kind == kind)
            .order_by(desc(AgentMemory.updated_at))
            .limit(80)
        )
    ).scalars().all()
    for memory in memories:
        overlap = jaccard(content_terms, tokenize(memory.content))
        if overlap >= 0.62 or normalize_text(memory.content) == normalize_text(content):
            return memory
    return None


async def trim_memories(session: AsyncSession, user_id: str) -> None:
    memories = (
        await session.execute(
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .order_by(desc(AgentMemory.updated_at))
            .offset(MAX_USER_MEMORIES)
        )
    ).scalars().all()
    for memory in memories:
        await session.delete(memory)


def memory_score(memory: AgentMemory, query_terms: set[str]) -> float:
    content_terms = tokenize(" ".join([memory.content, " ".join(memory.tags or [])]))
    overlap = len(query_terms & content_terms) if query_terms else 0
    kind_bonus = 0.8 if memory.kind in {"job_goal", "preference", "weakness"} else 0.4
    confidence_bonus = (memory.confidence or 70) / 100
    use_bonus = min(memory.use_count or 0, 8) * 0.05
    return overlap * 2.2 + kind_bonus + confidence_bonus + use_bonus


def should_consider_memory(user_message: str, assistant_reply: str) -> bool:
    text = f"{user_message}\n{assistant_reply}".strip()
    if len(text) < 12:
        return False
    if len(user_message.strip()) <= 5 and not any(word in user_message for word in ["我是", "我想", "我要", "目标", "简历", "面试", "投递"]):
        return False
    return True


def is_valid_memory_content(content: str) -> bool:
    if not 8 <= len(content) <= 220:
        return False
    if content.count("\n") > 1:
        return False
    blocked = ["密码", "验证码", "身份证", "银行卡", "token", "api key", "secret"]
    return not any(word.lower() in content.lower() for word in blocked)


def normalize_kind(kind: str) -> str:
    allowed = set(MEMORY_KIND_LABELS)
    return kind if kind in allowed else "episodic_summary"


def normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:24] for item in value if str(item).strip()][:6]


def merge_lists(left: list[str], right: list[str]) -> list[str]:
    seen: list[str] = []
    for item in [*left, *right]:
        clean = str(item).strip()
        if clean and clean not in seen:
            seen.append(clean)
    return seen[:8]


def merge_memory_text(left: str, right: str) -> str:
    left_clean = left.strip()
    right_clean = right.strip()
    if normalize_text(right_clean) in normalize_text(left_clean):
        return left_clean
    if normalize_text(left_clean) in normalize_text(right_clean):
        return right_clean
    return f"{left_clean}；{right_clean}"[:240]


def tokenize(value: str) -> set[str]:
    normalized = normalize_text(value)
    latin = re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{1,}", normalized)
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    grams: list[str] = []
    for chunk in chinese:
        grams.extend(chunk[index:index + 2] for index in range(max(1, len(chunk) - 1)))
        if len(chunk) <= 8:
            grams.append(chunk)
    return set(latin + grams)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value.lower().strip())


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0
    return len(left & right) / len(left | right)
