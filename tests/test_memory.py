from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.services.memory import (
    ARCHIVED_MEMORY_STATUS,
    PeachMemoryService,
    build_memory_context,
    explicit_memory_candidates,
    extract_entities,
    is_valid_memory_content,
    memory_hash,
    score_memory,
    tokenize,
)
from backend.app.models import AgentMemory, AgentMemoryEvent
from sqlalchemy import select


def test_memory_context_is_compact_and_labeled() -> None:
    memories = [
        SimpleNamespace(kind="job_goal", content="用户目标是 AI 产品经理。", tags=["目标"], use_count=0),
        SimpleNamespace(kind="weakness", content="用户面试时容易缺少量化结果。", tags=["面试"], use_count=0),
    ]

    context = build_memory_context(memories)

    assert "[求职目标]" in context
    assert "[薄弱点]" in context
    assert len(context) < 1200


def test_memory_filters_sensitive_or_low_value_content() -> None:
    assert is_valid_memory_content("用户目标是北京互联网公司的 AI 产品经理岗位。")
    assert not is_valid_memory_content("密码是 abc123456")
    assert not is_valid_memory_content("短")


def test_tokenize_supports_chinese_and_latin_terms() -> None:
    terms = tokenize("AIGC 产品经理 面试")

    assert "aigc" in terms
    assert "产品" in terms
    assert "面试" in terms


def test_memory_extracts_job_entities() -> None:
    entities = extract_entities("我想投字节跳动 AIGC 产品经理，北航项目经历要多讲。")

    assert "字节跳动" in "".join(entities["company"])
    assert "产品经理" in entities["role"]


def test_memory_scoring_uses_entity_and_keyword_signals() -> None:
    memory = SimpleNamespace(
        id="m1",
        kind="job_goal",
        content="用户目标是字节跳动 AIGC 产品经理岗位。",
        source="chat",
        confidence=90,
        tags=["字节跳动", "产品经理"],
        use_count=1,
        updated_at=datetime.now(timezone.utc),
        memory_metadata={
            "entities": {"company": ["字节跳动"], "role": ["产品经理"]},
            "bm25_terms": ["字节", "跳动", "产品", "经理", "aigc"],
        },
    )

    scored = score_memory(
        memory,
        "字节 AIGC 产品经理怎么准备",
        tokenize("字节 AIGC 产品经理怎么准备"),
        ["字节", "aigc", "产品", "经理"],
        {"company": ["字节跳动"], "role": ["产品经理"]},
        explain=True,
    )

    assert scored.score > 0.35
    assert scored.details["entity"] > 0


def test_memory_hash_normalizes_whitespace() -> None:
    assert memory_hash("用户 目标 是 AI 产品经理") == memory_hash("用户目标是AI产品经理")


@pytest.mark.asyncio
async def test_memory_service_add_raw_dedupes_by_hash(db_session) -> None:
    service = PeachMemoryService(db_session)
    result = await service.add(
        "用户目标是 AI 产品经理。",
        user_id="u-memory",
        source="test",
        metadata={"tags": ["目标"]},
        infer=False,
    )
    second = await service.add(
        "用户目标是AI产品经理。",
        user_id="u-memory",
        source="test",
        metadata={"tags": ["目标"]},
        infer=False,
    )
    await db_session.commit()

    assert len(result["results"]) == 1
    assert second["results"][0]["id"] == result["results"][0]["id"]


@pytest.mark.asyncio
async def test_memory_service_search_is_user_scoped(db_session) -> None:
    service = PeachMemoryService(db_session)
    await service.add("用户目标是腾讯产品经理。", user_id="u-a", source="test", infer=False)
    await service.add("用户目标是字节产品经理。", user_id="u-b", source="test", infer=False)
    await db_session.commit()

    result = await service.search("字节产品经理", user_id="u-a", top_k=3)

    assert all("字节" not in item["memory"] for item in result["results"])


def test_explicit_memory_candidate_extracts_remember_instruction() -> None:
    candidates = explicit_memory_candidates(
        [{"role": "user", "content": "记住：我喜欢压力型面试，后面模拟面试优先用这个风格。"}],
        "chat",
        {},
    )

    assert len(candidates) == 1
    assert candidates[0].kind == "preference"
    assert "压力型面试" in candidates[0].content
    assert candidates[0].confidence == 95


@pytest.mark.asyncio
async def test_memory_service_add_explicit_short_memory_without_llm(db_session) -> None:
    service = PeachMemoryService(db_session)
    result = await service.add(
        [{"role": "user", "content": "记住：压力型面试"}],
        user_id="u-explicit",
        source="chat",
        infer=True,
        profile=SimpleNamespace(id="u-explicit", name="同学"),
    )
    await db_session.commit()

    assert len(result["results"]) == 1
    assert "压力型面试" in result["results"][0]["memory"]


@pytest.mark.asyncio
async def test_memory_service_supersedes_changed_job_goal_and_records_events(db_session) -> None:
    service = PeachMemoryService(db_session)
    first = await service.add(
        "用户目标岗位是 AI 产品经理。",
        user_id="u-goal",
        source="test",
        metadata={"reason": "初始目标"},
        infer=False,
    )
    second = await service.add(
        "用户目标岗位是策略产品经理。",
        user_id="u-goal",
        source="test",
        metadata={"reason": "目标变化"},
        infer=False,
    )
    await db_session.commit()

    old_memory = await db_session.get(AgentMemory, first["results"][0]["id"])
    new_memory = await db_session.get(AgentMemory, second["results"][0]["id"])
    events = (
        await db_session.execute(
            select(AgentMemoryEvent)
            .where(AgentMemoryEvent.user_id == "u-goal")
            .order_by(AgentMemoryEvent.created_at)
        )
    ).scalars().all()

    assert old_memory.memory_metadata["status"] == ARCHIVED_MEMORY_STATUS
    assert old_memory.memory_metadata["superseded_by"] == new_memory.id
    assert new_memory.memory_metadata["status"] == "active"
    assert [event.event for event in events] == ["ADD", "ARCHIVE", "ADD"]

    search = await service.search("AI 产品经理", user_id="u-goal", top_k=5)
    assert all(item["id"] != old_memory.id for item in search["results"])
