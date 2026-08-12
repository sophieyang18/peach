from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.services.memory import (
    PeachMemoryService,
    build_memory_context,
    extract_entities,
    is_valid_memory_content,
    memory_hash,
    score_memory,
    tokenize,
)


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
