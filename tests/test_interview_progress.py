from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.app.models import AgentMemory, AgentMemoryEvent, InterviewSession, UserProfile
from backend.app.api.routes import build_interview_progress, normalize_tool_action, normalize_username
from backend.app.api.routes import cleanup_interview_related_data


def test_new_interview_has_zero_completion() -> None:
    interview = SimpleNamespace(transcript=[{"role": "interviewer", "content": "请先做自我介绍。"}])

    progress = build_interview_progress(interview)

    assert progress["answer_count"] == 0
    assert progress["completion"] == 0
    assert not progress["can_llm_finish"]
    assert all(not item["done"] for item in progress["checklist"])


def test_interview_cannot_finish_before_minimum_rounds() -> None:
    interview = SimpleNamespace(
        transcript=[
            {"role": "candidate", "content": "我是北航学生，做过 AI 产品项目。"},
            {"role": "candidate", "content": "我负责需求分析，推动上线，转化率提升 8%。"},
            {"role": "candidate", "content": "我理解产品经理要兼顾用户、业务和指标。"},
        ]
    )

    progress = build_interview_progress(interview)

    assert progress["answer_count"] == 3
    assert progress["completion"] > 0
    assert not progress["can_llm_finish"]


def test_tool_action_normalization_rejects_unknown_tool() -> None:
    action = normalize_tool_action({"tool": "drop_database", "payload": {"danger": True}}, 0)

    assert action["tool"] == "unsupported"
    assert action["approval_required"]
    assert action["payload"] == {}


def test_username_is_trimmed_and_bounded() -> None:
    assert normalize_username("  Apple01  ") == "Apple01"
    assert normalize_username("") == "demo"
    assert len(normalize_username("x" * 80)) == 40


@pytest.mark.asyncio
async def test_cleanup_interview_related_memory_is_scoped(db_session) -> None:
    profile = UserProfile(id="u-cleanup", username="Apple01", name="Apple01")
    interview = InterviewSession(
        id="iv-cleanup",
        user_id=profile.id,
        interview_type="mock",
        interviewer_style="不限",
        company="字节跳动",
        role="AI 产品经理",
        status="completed",
        transcript=[],
        report={"summary": "项目表达需要补充量化结果。"},
    )
    related = AgentMemory(
        id="mem-related",
        user_id=profile.id,
        kind="interview_pattern",
        content="字节跳动 AI 产品经理面试中，项目表达需要补充量化结果。",
        source="interview_report",
        memory_metadata={"interview_id": interview.id},
    )
    unrelated = AgentMemory(
        id="mem-unrelated",
        user_id=profile.id,
        kind="preference",
        content="用户喜欢先给结论再展开建议。",
        source="chat",
        memory_metadata={},
    )
    related_event = AgentMemoryEvent(
        id="event-related",
        user_id=profile.id,
        memory_id=related.id,
        event="ADD",
        new_content=related.content,
        source="interview_report",
        event_metadata={"interview_id": interview.id},
    )
    db_session.add_all([profile, interview, related, unrelated, related_event])
    await db_session.commit()

    await cleanup_interview_related_data(db_session, profile.id, interview)
    await db_session.commit()

    memories = (await db_session.execute(select(AgentMemory).where(AgentMemory.user_id == profile.id))).scalars().all()
    events = (await db_session.execute(select(AgentMemoryEvent).where(AgentMemoryEvent.user_id == profile.id))).scalars().all()

    assert [memory.id for memory in memories] == ["mem-unrelated"]
    assert events == []
