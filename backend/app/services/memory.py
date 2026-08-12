from __future__ import annotations

import hashlib
import logging
import math
import re
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import AgentMemory, AgentMemoryEvent, UserProfile
from backend.app.db import SessionLocal
from backend.app.services.agent import PeachAgent


logger = logging.getLogger(__name__)
MEMORY_LIMIT = 5
MAX_USER_MEMORIES = 120
SEARCH_POOL_SIZE = 160

MEMORY_KIND_LABELS = {
    "profile_fact": "用户事实",
    "preference": "沟通偏好",
    "job_goal": "求职目标",
    "target_company": "目标公司",
    "resume_signal": "简历信号",
    "project_signal": "项目信号",
    "skill_signal": "能力信号",
    "weakness": "薄弱点",
    "interview_pattern": "面试模式",
    "plan": "行动计划",
    "knowledge_fact": "知识事实",
    "episodic_summary": "阶段总结",
}

MEMORY_KIND_WEIGHTS = {
    "job_goal": 0.95,
    "target_company": 0.9,
    "weakness": 0.9,
    "resume_signal": 0.85,
    "project_signal": 0.85,
    "skill_signal": 0.8,
    "interview_pattern": 0.8,
    "preference": 0.75,
    "plan": 0.65,
    "profile_fact": 0.6,
    "knowledge_fact": 0.55,
    "episodic_summary": 0.45,
}
SUPERSEDING_KINDS = {"job_goal", "target_company"}
ACTIVE_MEMORY_STATUS = "active"
ARCHIVED_MEMORY_STATUS = "archived"

SENSITIVE_PATTERNS = [
    r"密码",
    r"验证码",
    r"身份证",
    r"银行卡",
    r"api\s*key",
    r"secret",
    r"token",
    r"\bsk-[a-zA-Z0-9_-]{12,}",
    r"\b\d{15,18}[xX]?\b",
    r"\b1[3-9]\d{9}\b",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
]

ENTITY_PATTERNS = {
    "company": r"[\u4e00-\u9fffA-Za-z0-9]{2,24}(?:公司|集团|科技)",
    "role": r"(?:AI|AIGC|大模型|策略|商业化|增长|C端|B端|平台)?产品经理|产品运营|数据分析|算法工程师|后端工程师",
    "school": r"[\u4e00-\u9fff]{2,20}(?:大学|学院)",
    "skill": r"(?:SQL|Python|AIGC|LLM|RAG|PRD|Axure|Figma|数据分析|用户研究|需求分析|竞品分析|增长|推荐|搜索)",
}
KNOWN_COMPANIES = ["字节跳动", "腾讯", "阿里", "快手", "美团", "百度", "小红书", "京东", "网易", "米哈游", "华为"]


@dataclass
class MemoryCandidate:
    kind: str
    content: str
    source: str
    confidence: int = 70
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredMemory:
    memory: AgentMemory
    score: float
    details: dict[str, float]


class PeachMemoryService:
    """A lightweight mem0-style memory layer for Peach.

    It keeps the public add/search shape of mem0 while staying inside the
    project's SQLAlchemy storage. The retrieval path fuses token overlap,
    BM25-ish keyword scoring, entity boosts, recency, confidence and use count.
    """

    def __init__(self, session: AsyncSession, agent: PeachAgent | None = None) -> None:
        self.session = session
        self.agent = agent

    async def add(
        self,
        messages: str | dict[str, Any] | list[dict[str, Any]],
        *,
        user_id: str,
        source: str = "chat",
        metadata: dict[str, Any] | None = None,
        infer: bool = True,
        profile: UserProfile | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        normalized = normalize_messages(messages)
        if not normalized:
            return {"results": []}

        if infer:
            candidates = explicit_memory_candidates(normalized, source, metadata or {})
        else:
            candidates = []

        if infer and self.agent and profile and not candidates:
            inferred = await self._infer_candidates(normalized, user_id, source, metadata or {}, profile)
            candidates = dedupe_candidates([*candidates, *inferred])
        elif not candidates:
            candidates = [
                MemoryCandidate(
                    kind=infer_memory_kind_from_text(item["content"], source),
                    content=item["content"],
                    source=source,
                    tags=normalize_tags((metadata or {}).get("tags")),
                    metadata=metadata or {},
                )
                for item in normalized
                if item.get("role") != "system"
            ]

        results: list[dict[str, Any]] = []
        for candidate in candidates:
            memory = await self._add_candidate(user_id, candidate)
            if memory:
                await self.session.flush()
                await self.session.refresh(memory)
                results.append(to_memory_result(memory, getattr(memory, "_peach_memory_event", "ADD")))

        if results:
            await self.trim(user_id)
        return {"results": results}

    async def search(
        self,
        query: str,
        *,
        user_id: str,
        top_k: int = MEMORY_LIMIT,
        filters: dict[str, Any] | None = None,
        explain: bool = False,
        touch: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        query = (query or "").strip()
        if not query:
            return {"results": []}

        memories = await self._load_pool(user_id, filters or {})
        if not memories:
            return {"results": []}

        query_terms = tokenize(query)
        query_entities = extract_entities(query)
        query_bm25_terms = bm25_terms(query)

        scored = [
            score_memory(memory, query, query_terms, query_bm25_terms, query_entities, explain=explain)
            for memory in memories
        ]
        scored = [item for item in scored if item.score > 0]
        if not scored:
            scored = [
                score_memory(memory, query, query_terms, query_bm25_terms, query_entities, explain=explain, fallback=True)
                for memory in memories[: min(top_k, 3)]
            ]

        scored.sort(key=lambda item: item.score, reverse=True)
        selected = scored[:top_k]
        if touch:
            now = datetime.now(timezone.utc)
            for item in selected:
                item.memory.use_count = (item.memory.use_count or 0) + 1
                item.memory.last_used_at = now

        return {
            "results": [
                to_memory_result(item.memory, score=item.score, details=item.details if explain else None)
                for item in selected
            ]
        }

    async def get_all(
        self,
        *,
        user_id: str,
        top_k: int = 80,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        memories = await self._load_pool(user_id, filters or {}, limit=top_k)
        return {"results": [to_memory_result(memory) for memory in memories[:top_k]]}

    async def delete(self, memory_id: str, *, user_id: str) -> bool:
        memory = await self.session.get(AgentMemory, memory_id)
        if not memory or memory.user_id != user_id:
            return False
        await self._record_event(
            user_id,
            memory.id,
            "DELETE",
            old_content=memory.content,
            new_content="",
            source=memory.source,
            reason="用户删除长期记忆",
        )
        await self.session.delete(memory)
        return True

    async def trim(self, user_id: str) -> None:
        memories = (
            await self.session.execute(
                select(AgentMemory)
                .where(AgentMemory.user_id == user_id)
                .order_by(desc(AgentMemory.updated_at))
                .offset(MAX_USER_MEMORIES)
            )
        ).scalars().all()
        for memory in memories:
            await self.session.delete(memory)

    async def _infer_candidates(
        self,
        messages: list[dict[str, str]],
        user_id: str,
        source: str,
        metadata: dict[str, Any],
        profile: UserProfile,
    ) -> list[MemoryCandidate]:
        if not should_consider_memory(messages):
            return []

        user_text = "\n".join(item["content"] for item in messages if item.get("role") == "user")
        assistant_text = "\n".join(item["content"] for item in messages if item.get("role") == "assistant")
        context = {
            **metadata,
            "last_messages": messages[-8:],
            "existing_memories": [to_memory_result(item) for item in await self._similar_existing(user_id, user_text)],
        }
        try:
            raw_candidates = await self.agent.extract_memories(
                profile,
                source=source,
                user_message=user_text,
                assistant_reply=assistant_text,
                context=context,
            )
        except Exception as exc:
            logger.warning("memory inference skipped for user %s: %s", user_id, exc)
            return []

        candidates: list[MemoryCandidate] = []
        for item in raw_candidates[:6]:
            content = str(item.get("content") or "").strip()
            if not is_valid_memory_content(content):
                continue
            entities = extract_entities(content)
            tags = normalize_tags([*as_list(item.get("tags")), *flatten_entities(entities)])
            candidates.append(
                MemoryCandidate(
                    kind=normalize_kind(str(item.get("kind") or "episodic_summary")),
                    content=content,
                    source=source,
                    confidence=clamp_int(item.get("confidence"), 0, 100, default=70),
                    tags=tags,
                    metadata={
                        **metadata,
                        "reason": str(item.get("reason") or "")[:240],
                        "extracted_from": source,
                        "entities": entities,
                        "hash": memory_hash(content),
                        "created_by": "peach_memory_v2",
                    },
                )
            )
        return dedupe_candidates(candidates)

    async def _add_candidate(self, user_id: str, candidate: MemoryCandidate) -> AgentMemory | None:
        candidate.content = normalize_memory_sentence(candidate.content)
        is_explicit = candidate.metadata.get("created_by") == "peach_explicit_memory"
        if is_explicit:
            valid_content = is_valid_explicit_memory_content(candidate.content)
        else:
            valid_content = is_valid_memory_content(candidate.content)
        if not valid_content:
            return None

        existing = await self._find_duplicate(user_id, candidate)
        if existing:
            old_content = existing.content
            existing.content = merge_memory_text(existing.content, candidate.content)
            existing.source = candidate.source or existing.source
            existing.confidence = max(int(existing.confidence or 0), candidate.confidence)
            existing.tags = merge_lists(existing.tags or [], candidate.tags)
            existing.memory_metadata = {
                **merge_metadata(existing.memory_metadata or {}, candidate.metadata),
                "status": ACTIVE_MEMORY_STATUS,
                "superseded_by": "",
            }
            event = "UPDATE" if normalize_text(old_content) != normalize_text(existing.content) else "NONE"
            setattr(existing, "_peach_memory_event", event)
            await self._record_event(
                user_id,
                existing.id,
                event,
                old_content=old_content,
                new_content=existing.content,
                source=candidate.source,
                reason=str(candidate.metadata.get("reason") or "相似记忆合并"),
                metadata={"candidate_kind": candidate.kind},
            )
            return existing

        superseded = await self._find_superseded(user_id, candidate)

        memory = AgentMemory(
            user_id=user_id,
            kind=candidate.kind,
            content=candidate.content,
            source=candidate.source,
            confidence=max(0, min(100, candidate.confidence)),
            tags=candidate.tags[:8],
            memory_metadata={
                **candidate.metadata,
                "hash": candidate.metadata.get("hash") or memory_hash(candidate.content),
                "text_terms": sorted(tokenize(candidate.content))[:80],
                "bm25_terms": bm25_terms(candidate.content)[:80],
                "schema": "peach_memory_v2",
                "status": ACTIVE_MEMORY_STATUS,
                "supersedes": [item.id for item in superseded],
            },
        )
        self.session.add(memory)
        await self.session.flush()
        setattr(memory, "_peach_memory_event", "ADD")
        for old_memory in superseded:
            await self._archive_memory(
                user_id,
                old_memory,
                superseded_by=memory.id,
                source=candidate.source,
                reason=f"被新的{MEMORY_KIND_LABELS.get(candidate.kind, candidate.kind)}替换",
            )
        await self._record_event(
            user_id,
            memory.id,
            "ADD",
            old_content="",
            new_content=memory.content,
            source=candidate.source,
            reason=str(candidate.metadata.get("reason") or "新增长期记忆"),
            metadata={"candidate_kind": candidate.kind, "supersedes": [item.id for item in superseded]},
        )
        return memory

    async def _find_duplicate(self, user_id: str, candidate: MemoryCandidate) -> AgentMemory | None:
        content_hash = candidate.metadata.get("hash") or memory_hash(candidate.content)
        memories = (
            await self.session.execute(
                select(AgentMemory)
                .where(AgentMemory.user_id == user_id)
                .where(AgentMemory.kind == candidate.kind)
                .order_by(desc(AgentMemory.updated_at))
                .limit(SEARCH_POOL_SIZE)
            )
        ).scalars().all()

        candidate_terms = tokenize(candidate.content)
        candidate_entities = extract_entities(candidate.content)
        for memory in memories:
            if is_archived_memory(memory):
                continue
            meta = memory.memory_metadata or {}
            if meta.get("hash") == content_hash:
                return memory
            overlap = jaccard(candidate_terms, tokenize(memory.content))
            entity_overlap = entity_jaccard(candidate_entities, extract_memory_entities(memory))
            if overlap >= 0.72 or (overlap >= 0.45 and entity_overlap >= 0.5):
                return memory
            if normalize_text(memory.content) == normalize_text(candidate.content):
                return memory
        return None

    async def _find_superseded(self, user_id: str, candidate: MemoryCandidate) -> list[AgentMemory]:
        if not can_supersede_existing_memory(candidate):
            return []
        memories = (
            await self.session.execute(
                select(AgentMemory)
                .where(AgentMemory.user_id == user_id)
                .where(AgentMemory.kind == candidate.kind)
                .order_by(desc(AgentMemory.updated_at))
                .limit(SEARCH_POOL_SIZE)
            )
        ).scalars().all()
        candidate_dimension = memory_dimension(candidate.kind, candidate.content)
        superseded: list[AgentMemory] = []
        for memory in memories:
            if is_archived_memory(memory):
                continue
            if memory_dimension(memory.kind, memory.content) != candidate_dimension:
                continue
            if memory_hash(memory.content) == memory_hash(candidate.content):
                continue
            superseded.append(memory)
        return superseded[:6]

    async def _archive_memory(
        self,
        user_id: str,
        memory: AgentMemory,
        *,
        superseded_by: str,
        source: str,
        reason: str,
    ) -> None:
        metadata = dict(memory.memory_metadata or {})
        if metadata.get("status") == ARCHIVED_MEMORY_STATUS:
            return
        old_content = memory.content
        memory.memory_metadata = {
            **metadata,
            "status": ARCHIVED_MEMORY_STATUS,
            "superseded_by": superseded_by,
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._record_event(
            user_id,
            memory.id,
            "ARCHIVE",
            old_content=old_content,
            new_content=memory.content,
            source=source,
            reason=reason,
            metadata={"superseded_by": superseded_by},
        )

    async def _record_event(
        self,
        user_id: str,
        memory_id: str,
        event: str,
        *,
        old_content: str,
        new_content: str,
        source: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AgentMemoryEvent(
                user_id=user_id,
                memory_id=memory_id,
                event=event,
                old_content=old_content[:1000],
                new_content=new_content[:1000],
                source=source[:80],
                reason=reason[:500],
                event_metadata=metadata or {},
            )
        )

    async def _similar_existing(self, user_id: str, query: str) -> list[AgentMemory]:
        result = await self.search(query or "用户记忆", user_id=user_id, top_k=8)
        ids = [item["id"] for item in result["results"]]
        if not ids:
            return []
        memories = (
            await self.session.execute(select(AgentMemory).where(AgentMemory.id.in_(ids)))
        ).scalars().all()
        by_id = {item.id: item for item in memories}
        return [by_id[item_id] for item_id in ids if item_id in by_id]

    async def _load_pool(
        self,
        user_id: str,
        filters: dict[str, Any],
        limit: int = SEARCH_POOL_SIZE,
    ) -> list[AgentMemory]:
        stmt = select(AgentMemory).where(AgentMemory.user_id == user_id)
        kind = filters.get("kind")
        if kind:
            allowed = set(as_list(kind))
            stmt = stmt.where(AgentMemory.kind.in_(allowed))
        source = filters.get("source")
        if source:
            allowed = set(as_list(source))
            stmt = stmt.where(AgentMemory.source.in_(allowed))
        include_archived = bool(filters.get("include_archived"))
        memories = list((await self.session.execute(stmt.order_by(desc(AgentMemory.updated_at)).limit(limit))).scalars().all())
        if include_archived:
            return memories
        return [memory for memory in memories if not is_archived_memory(memory)]


async def retrieve_relevant_memories(
    session: AsyncSession,
    user_id: str,
    query: str,
    limit: int = MEMORY_LIMIT,
) -> list[AgentMemory]:
    service = PeachMemoryService(session)
    result = await service.search(query, user_id=user_id, top_k=limit)
    ids = [item["id"] for item in result["results"]]
    if not ids:
        return []
    memories = (await session.execute(select(AgentMemory).where(AgentMemory.id.in_(ids)))).scalars().all()
    by_id = {memory.id: memory for memory in memories}
    return [by_id[item_id] for item_id in ids if item_id in by_id]


def build_memory_context(memories: list[AgentMemory]) -> str:
    if not memories:
        return "暂无可用长期记忆。"
    lines = []
    for memory in memories[:MEMORY_LIMIT]:
        label = MEMORY_KIND_LABELS.get(memory.kind, memory.kind or "记忆")
        tags = "、".join(memory.tags or [])
        entities = flatten_entities(extract_memory_entities(memory))
        entity_suffix = f"｜实体：{'、'.join(entities[:4])}" if entities else ""
        suffix = f"（{tags}{entity_suffix}）" if tags or entity_suffix else ""
        lines.append(f"- [{label}] {memory.content}{suffix}")
    return "\n".join(lines)[:1400]


async def remember_interaction(
    session: AsyncSession,
    agent: PeachAgent,
    profile: UserProfile,
    source: str,
    user_message: str,
    assistant_reply: str = "",
    context: dict[str, Any] | None = None,
) -> list[AgentMemory]:
    try:
        service = PeachMemoryService(session, agent)
        result = await asyncio.wait_for(
            service.add(
                [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_reply},
                ],
                user_id=profile.id,
                source=source,
                metadata=context or {},
                infer=True,
                profile=profile,
            ),
            timeout=1.5,
        )
        ids = [item["id"] for item in result["results"]]
        if not ids:
            return []
        memories = (await session.execute(select(AgentMemory).where(AgentMemory.id.in_(ids)))).scalars().all()
        by_id = {memory.id: memory for memory in memories}
        return [by_id[item_id] for item_id in ids if item_id in by_id]
    except Exception as exc:
        logger.warning("memory write skipped for user %s: %r", profile.id, exc)
        return []


async def remember_interaction_isolated(
    agent: PeachAgent,
    *,
    user_id: str,
    username: str,
    profile_snapshot: dict[str, Any],
    source: str,
    user_message: str,
    assistant_reply: str = "",
    context: dict[str, Any] | None = None,
) -> list[AgentMemory]:
    """Write memory in a separate transaction so chat/interview writes are never rolled back."""

    async with SessionLocal() as session:
        profile = SimpleNamespace(
            id=user_id,
            username=username,
            name=str(profile_snapshot.get("name") or "同学"),
            target_role=str(profile_snapshot.get("target_role") or "产品经理"),
            target_company=str(profile_snapshot.get("target_company") or ""),
            target_city=str(profile_snapshot.get("target_city") or ""),
            stage=str(profile_snapshot.get("stage") or "投递期"),
            resume_text=str(profile_snapshot.get("resume_text") or ""),
            communication_style=str(profile_snapshot.get("communication_style") or "温暖直接"),
            strengths=list(profile_snapshot.get("strengths") or []),
            weak_points=list(profile_snapshot.get("weak_points") or []),
            plan=list(profile_snapshot.get("plan") or []),
        )
        try:
            memories = await remember_interaction(
                session,
                agent,
                profile,
                source=source,
                user_message=user_message,
                assistant_reply=assistant_reply,
                context=context,
            )
            await session.commit()
            return memories
        except Exception as exc:
            logger.warning("isolated memory write skipped for user %s: %r", user_id, exc)
            await session.rollback()
            return []


async def upsert_memory(session: AsyncSession, user_id: str, data: dict[str, Any]) -> AgentMemory:
    service = PeachMemoryService(session)
    candidate = MemoryCandidate(
        kind=normalize_kind(str(data.get("kind") or "episodic_summary")),
        content=str(data.get("content") or ""),
        source=str(data.get("source") or "chat"),
        confidence=clamp_int(data.get("confidence"), 0, 100, default=70),
        tags=normalize_tags(data.get("tags")),
        metadata=data.get("memory_metadata") or {},
    )
    memory = await service._add_candidate(user_id, candidate)
    if memory is None:
        raise ValueError("invalid memory content")
    return memory


async def find_similar_memory(session: AsyncSession, user_id: str, content: str, kind: str) -> AgentMemory | None:
    service = PeachMemoryService(session)
    return await service._find_duplicate(
        user_id,
        MemoryCandidate(kind=normalize_kind(kind), content=content, source="manual", metadata={"hash": memory_hash(content)}),
    )


async def trim_memories(session: AsyncSession, user_id: str) -> None:
    await PeachMemoryService(session).trim(user_id)


def score_memory(
    memory: AgentMemory,
    query: str,
    query_terms: set[str],
    query_bm25_terms: list[str],
    query_entities: dict[str, list[str]],
    *,
    explain: bool = False,
    fallback: bool = False,
) -> ScoredMemory:
    memory_terms = tokenize(" ".join([memory.content, " ".join(memory.tags or [])]))
    semantic = jaccard(query_terms, memory_terms)
    keyword = bm25_like_score(query_bm25_terms, memory)
    entity = entity_jaccard(query_entities, extract_memory_entities(memory))
    kind = MEMORY_KIND_WEIGHTS.get(memory.kind, 0.4)
    confidence = (memory.confidence or 70) / 100
    recency = recency_score(memory.updated_at)
    usage = min(memory.use_count or 0, 10) / 10

    if fallback:
        semantic = max(semantic, 0.05)
        recency = max(recency, 0.45)

    score = (
        semantic * 0.34
        + keyword * 0.24
        + entity * 0.18
        + kind * 0.08
        + confidence * 0.06
        + recency * 0.06
        + usage * 0.04
    )
    if query and normalize_text(query) in normalize_text(memory.content):
        score += 0.12
    score = min(score, 1.0)
    details = {
        "semantic": round(semantic, 4),
        "keyword": round(keyword, 4),
        "entity": round(entity, 4),
        "kind": round(kind, 4),
        "confidence": round(confidence, 4),
        "recency": round(recency, 4),
        "usage": round(usage, 4),
        "final": round(score, 4),
    }
    return ScoredMemory(memory=memory, score=score, details=details if explain else {})


def memory_score(memory: AgentMemory, query_terms: set[str]) -> float:
    query = " ".join(sorted(query_terms))
    return score_memory(memory, query, query_terms, list(query_terms), extract_entities(query)).score


def normalize_messages(messages: str | dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, str]]:
    if isinstance(messages, str):
        raw_items = [{"role": "user", "content": messages}]
    elif isinstance(messages, dict):
        raw_items = [messages]
    elif isinstance(messages, list):
        raw_items = messages
    else:
        return []

    normalized: list[dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").strip() or "user"
        content = str(item.get("content") or "").strip()
        if content:
            normalized.append({"role": role, "content": content})
    return normalized


def should_consider_memory(messages: str | list[dict[str, str]], assistant_reply: str = "") -> bool:
    if isinstance(messages, str):
        text = f"{messages}\n{assistant_reply}".strip()
        user_text = messages.strip()
    else:
        text = "\n".join(item.get("content", "") for item in messages).strip()
        user_text = "\n".join(item.get("content", "") for item in messages if item.get("role") == "user").strip()
    if len(text) < 12:
        return False
    if len(user_text) <= 5 and not any(word in user_text for word in ["我是", "我想", "我要", "目标", "简历", "面试", "投递"]):
        return False
    return True


EXPLICIT_MEMORY_PATTERNS = [
    r"(?:请你|你要|帮我)?记住[:：,， ]*(.+)",
    r"(?:请你|你要|帮我)?记一下[:：,， ]*(.+)",
    r"(?:以后|之后)?(?:要)?记得[:：,， ]*(.+)",
    r"别忘了[:：,， ]*(.+)",
    r"帮我记(?:住|一下)?[:：,， ]*(.+)",
]


def explicit_memory_candidates(
    messages: list[dict[str, str]],
    source: str,
    metadata: dict[str, Any],
) -> list[MemoryCandidate]:
    user_text = "\n".join(item.get("content", "") for item in messages if item.get("role") == "user").strip()
    content = extract_explicit_memory_text(user_text)
    if not content:
        return []
    content = normalize_memory_sentence(content)
    if not is_valid_explicit_memory_content(content):
        return []
    entities = extract_entities(content)
    kind = infer_explicit_memory_kind(content)
    return [
        MemoryCandidate(
            kind=kind,
            content=content,
            source=f"{source}:explicit",
            confidence=95,
            tags=normalize_tags(["explicit_memory", *flatten_entities(entities)]),
            metadata={
                **metadata,
                "reason": "用户明确要求桃子记住这条信息",
                "entities": entities,
                "hash": memory_hash(content),
                "created_by": "peach_explicit_memory",
            },
        )
    ]


def extract_explicit_memory_text(text: str) -> str:
    text = (text or "").strip()
    for pattern in EXPLICIT_MEMORY_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return clean_explicit_memory_text(match.group(1))
    return ""


def clean_explicit_memory_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    text = re.split(r"(?:。|\n|$)", text, maxsplit=1)[0].strip()
    return text.strip(" ：:，,。.")


def infer_explicit_memory_kind(content: str) -> str:
    inferred = infer_memory_kind_from_text(content)
    if inferred != "episodic_summary":
        return inferred
    return "profile_fact"


def infer_memory_kind_from_text(content: str, source: str = "") -> str:
    if "面试" in source and any(word in content for word in ["卡", "不会", "紧张", "追问", "答得", "薄弱", "复盘"]):
        return "interview_pattern"
    if any(word in content for word in ["目标", "想投", "意向", "岗位", "公司", "秋招", "实习"]):
        return "job_goal"
    if any(word in content for word in ["喜欢", "偏好", "希望", "不要", "别", "语气", "风格", "压力型", "温和型"]):
        return "preference"
    if any(word in content for word in ["不擅长", "薄弱", "容易", "紧张", "卡", "问题", "短板"]):
        return "weakness"
    if any(word in content for word in ["做过", "负责", "主导", "项目", "实习", "能力", "会用"]):
        return "skill_signal"
    if any(word in content for word in ["学校", "大学", "专业", "年级", "背景"]):
        return "profile_fact"
    return "episodic_summary"


def is_valid_memory_content(content: str) -> bool:
    content = (content or "").strip()
    if not 8 <= len(content) <= 240:
        return False
    if content.count("\n") > 1:
        return False
    lowered = content.lower()
    return not any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in SENSITIVE_PATTERNS)


def is_valid_explicit_memory_content(content: str) -> bool:
    content = (content or "").strip()
    if not 4 <= len(content) <= 240:
        return False
    lowered = content.lower()
    return not any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in SENSITIVE_PATTERNS)


def normalize_kind(kind: str) -> str:
    return kind if kind in MEMORY_KIND_LABELS else "episodic_summary"


def normalize_tags(value: Any) -> list[str]:
    items = as_list(value)
    cleaned: list[str] = []
    for item in items:
        clean = str(item).strip()[:24]
        if clean and clean not in cleaned and is_valid_tag(clean):
            cleaned.append(clean)
    return cleaned[:8]


def is_valid_tag(tag: str) -> bool:
    return not any(re.search(pattern, tag, flags=re.IGNORECASE) for pattern in SENSITIVE_PATTERNS)


def merge_lists(left: list[str], right: list[str]) -> list[str]:
    seen: list[str] = []
    for item in [*left, *right]:
        clean = str(item).strip()
        if clean and clean not in seen:
            seen.append(clean)
    return seen[:10]


def merge_metadata(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = {**left, **right}
    merged["entities"] = merge_entities(left.get("entities") or {}, right.get("entities") or {})
    merged["previous_hashes"] = merge_lists(as_list(left.get("previous_hashes")), [left.get("hash"), right.get("hash")])
    merged["updated_by"] = "peach_memory_v2"
    return merged


def merge_memory_text(left: str, right: str) -> str:
    left_clean = normalize_memory_sentence(left)
    right_clean = normalize_memory_sentence(right)
    if normalize_text(right_clean) in normalize_text(left_clean):
        return left_clean
    if normalize_text(left_clean) in normalize_text(right_clean):
        return right_clean
    return f"{left_clean}；{right_clean}"[:260]


def is_archived_memory(memory: AgentMemory) -> bool:
    return (memory.memory_metadata or {}).get("status") == ARCHIVED_MEMORY_STATUS


def can_supersede_existing_memory(candidate: MemoryCandidate) -> bool:
    if candidate.kind in SUPERSEDING_KINDS:
        return True
    if candidate.kind == "preference":
        return memory_dimension(candidate.kind, candidate.content) != "preference:general"
    return False


def memory_dimension(kind: str, content: str) -> str:
    text = normalize_text(content)
    if kind == "job_goal":
        if any(word in content for word in ["公司", "字节", "腾讯", "阿里", "快手", "美团", "百度", "小红书"]):
            return "job_goal:company"
        if any(word in content for word in ["岗位", "产品经理", "产品运营", "算法", "后端", "数据分析"]):
            return "job_goal:role"
        if any(word in content for word in ["城市", "北京", "上海", "深圳", "杭州", "广州"]):
            return "job_goal:city"
        return "job_goal:general"
    if kind == "target_company":
        return "target_company"
    if kind == "preference":
        if any(word in content for word in ["面试风格", "压力型", "温和型", "拷打", "严格"]):
            return "preference:interview_style"
        if any(word in content for word in ["语气", "直接", "温柔", "犀利", "鼓励"]):
            return "preference:communication_tone"
        if any(word in content for word in ["语速", "慢", "快", "中速"]):
            return "preference:speech_rate"
        if "不要" in content or "别" in content:
            return f"preference:avoid:{text[:16]}"
        return "preference:general"
    return kind


def normalize_memory_sentence(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).replace("；；", "；")[:260]


def tokenize(value: str) -> set[str]:
    normalized = normalize_text(value)
    latin = re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{1,}", normalized)
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    grams: list[str] = []
    for chunk in chinese:
        grams.extend(chunk[index:index + 2] for index in range(max(1, len(chunk) - 1)))
        if len(chunk) <= 10:
            grams.append(chunk)
    return set(latin + grams)


def bm25_terms(value: str) -> list[str]:
    latin = re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{1,}", value.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", value)
    terms = [*latin]
    for chunk in chinese:
        terms.extend(chunk[index:index + 2] for index in range(max(1, len(chunk) - 1)))
        if len(chunk) <= 8:
            terms.append(chunk)
    return [term for term in terms if len(term) >= 2]


def bm25_like_score(query_terms: list[str], memory: AgentMemory) -> float:
    if not query_terms:
        return 0
    meta_terms = as_list((memory.memory_metadata or {}).get("bm25_terms"))
    doc_terms = meta_terms or bm25_terms(" ".join([memory.content, " ".join(memory.tags or [])]))
    if not doc_terms:
        return 0
    freq = {term: doc_terms.count(term) for term in set(doc_terms)}
    doc_len = len(doc_terms)
    avg_len = 32
    k1 = 1.2
    b = 0.75
    score = 0.0
    for term in set(query_terms):
        tf = freq.get(term, 0)
        if not tf:
            continue
        score += ((k1 + 1) * tf) / (k1 * (1 - b + b * doc_len / avg_len) + tf)
    midpoint, steepness = bm25_params(len(set(query_terms)))
    return 1.0 / (1.0 + math.exp(-steepness * (score - midpoint)))


def bm25_params(num_terms: int) -> tuple[float, float]:
    if num_terms <= 3:
        return 1.2, 1.1
    if num_terms <= 6:
        return 1.8, 0.9
    return 2.4, 0.7


def extract_entities(value: str) -> dict[str, list[str]]:
    entities: dict[str, list[str]] = {}
    for kind, pattern in ENTITY_PATTERNS.items():
        matches = []
        for match in re.findall(pattern, value, flags=re.IGNORECASE):
            clean = str(match).strip()
            if clean and clean not in matches:
                matches.append(clean)
        if matches:
            entities[kind] = matches[:8]
    company_matches = [company for company in KNOWN_COMPANIES if company.lower() in value.lower()]
    if company_matches:
        entities["company"] = merge_lists(company_matches, entities.get("company") or [])
    return entities


def extract_memory_entities(memory: AgentMemory) -> dict[str, list[str]]:
    metadata = getattr(memory, "memory_metadata", None) or {}
    entities = metadata.get("entities")
    if isinstance(entities, dict):
        return {str(key): normalize_tags(value) for key, value in entities.items()}
    return extract_entities(" ".join([memory.content, " ".join(memory.tags or [])]))


def merge_entities(left: dict[str, Any], right: dict[str, Any]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for key in set(left) | set(right):
        merged[str(key)] = merge_lists(as_list(left.get(key)), as_list(right.get(key)))
    return {key: value for key, value in merged.items() if value}


def flatten_entities(entities: dict[str, list[str]]) -> list[str]:
    flattened: list[str] = []
    for values in entities.values():
        for value in values:
            if value not in flattened:
                flattened.append(value)
    return flattened[:12]


def entity_jaccard(left: dict[str, list[str]], right: dict[str, list[str]]) -> float:
    left_items = {normalize_text(item) for item in flatten_entities(left)}
    right_items = {normalize_text(item) for item in flatten_entities(right)}
    return jaccard(left_items, right_items)


def recency_score(value: datetime | None) -> float:
    if not value:
        return 0.2
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    days = max(0.0, (datetime.now(timezone.utc) - value).total_seconds() / 86400)
    return 1.0 / (1.0 + days / 14)


def to_memory_result(
    memory: AgentMemory,
    event: str | None = None,
    score: float | None = None,
    details: dict[str, float] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": memory.id,
        "memory": memory.content,
        "kind": memory.kind,
        "source": memory.source,
        "confidence": memory.confidence,
        "tags": memory.tags or [],
        "metadata": memory.memory_metadata or {},
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
        "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
    }
    if event:
        result["event"] = event
    if score is not None:
        result["score"] = round(float(score), 4)
    if details:
        result["score_details"] = details
    return result


def dedupe_candidates(candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
    seen: set[str] = set()
    deduped: list[MemoryCandidate] = []
    for candidate in candidates:
        key = f"{candidate.kind}:{memory_hash(candidate.content)}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped[:5]


def memory_hash(content: str) -> str:
    return hashlib.md5(normalize_text(content).encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value).lower().strip())


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0
    return len(left & right) / len(left | right)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def clamp_int(value: Any, minimum: int, maximum: int, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
