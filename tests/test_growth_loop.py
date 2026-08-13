from sqlalchemy import select

import pytest

from backend.app.models import (
    ActionState,
    AgentMemory,
    GrowthIssue,
    HomeRecommendation,
    InterviewSession,
    UserAbilityScore,
    UserProfile,
)
from backend.app.services.growth import apply_interview_growth_update, build_growth_center, build_home_context
from backend.app.services.recommendations import refresh_home_recommendations, should_refresh_recommendations
from backend.app.api.routes import has_profile_recommendation_signal


@pytest.mark.asyncio
async def test_interview_growth_update_persists_user_scoped_loop(db_session) -> None:
    profile = UserProfile(
        id="u-growth-a",
        username="Apple01",
        name="Apple01",
        target_role="AI 产品经理",
        target_company="字节跳动",
        resume_text="负责 AIGC 广告素材二创工具，提升创作者选材效率。",
    )
    other_profile = UserProfile(id="u-growth-b", username="Banana052", name="Banana052")
    db_session.add_all([profile, other_profile])
    interview = InterviewSession(
        id="iv-growth-a",
        user_id=profile.id,
        interview_type="mock",
        interviewer_style="温和型",
        company="字节跳动",
        role="AI 产品经理",
        status="completed",
        transcript=[
            {"role": "interviewer", "content": "请先介绍你最近的项目。"},
            {
                "role": "candidate",
                "content": "我做过广告素材二创工具，主要讲了方案，但决策依据和数据归因说得不够完整。",
            },
        ],
        report={
            "summary": "候选人能说明项目背景，但项目决策依据、指标归因和业务价值还不够充分。",
            "dimensions": [
                {"name": "语言流畅度", "score": 78},
                {"name": "语言精简度", "score": 72},
                {"name": "岗位核心能力", "score": 68},
            ],
            "key_improvements": ["补充为什么这么做和指标结果归因。"],
            "question_review": [
                {
                    "question": "为什么做这个方向？",
                    "candidate_transcript": "我当时主要看到了用户素材选择很麻烦。",
                }
            ],
        },
    )
    db_session.add(interview)

    update = await apply_interview_growth_update(db_session, profile, interview)
    await db_session.commit()

    assert update.abilities
    assert update.issues
    assert update.memory_updates
    assert update.actions
    assert interview.report["growth_findings"]
    assert interview.report["next_actions"]

    scores = (
        await db_session.execute(select(UserAbilityScore).where(UserAbilityScore.user_id == profile.id))
    ).scalars().all()
    issues = (
        await db_session.execute(select(GrowthIssue).where(GrowthIssue.user_id == profile.id))
    ).scalars().all()
    actions = (
        await db_session.execute(select(ActionState).where(ActionState.user_id == profile.id))
    ).scalars().all()
    memories = (
        await db_session.execute(select(AgentMemory).where(AgentMemory.user_id == profile.id))
    ).scalars().all()
    other_memories = (
        await db_session.execute(select(AgentMemory).where(AgentMemory.user_id == other_profile.id))
    ).scalars().all()

    assert len(scores) >= 4
    assert any(issue.issue_key == "project_decision_reasoning" for issue in issues)
    assert actions[0].target_issue_id == issues[0].id
    assert any(memory.kind == "interview_pattern" for memory in memories)
    assert other_memories == []


@pytest.mark.asyncio
async def test_home_context_and_growth_center_use_growth_state(db_session) -> None:
    profile = UserProfile(id="u-growth-home", username="Cherry07", name="Cherry07", target_role="产品经理")
    db_session.add(profile)
    interview = InterviewSession(
        id="iv-growth-home",
        user_id=profile.id,
        interview_type="mock",
        interviewer_style="压力型",
        company="目标公司",
        role="产品经理",
        status="completed",
        transcript=[{"role": "candidate", "content": "项目结果有提升，但我没有讲清楚为什么这样决策。"}],
        report={
            "summary": "项目决策依据不足。",
            "dimensions": [{"name": "岗位核心能力", "score": 70}],
            "key_improvements": ["围绕项目决策依据做专项训练。"],
            "question_review": [],
        },
    )
    db_session.add(interview)
    await apply_interview_growth_update(db_session, profile, interview)
    await db_session.commit()

    home = await build_home_context(db_session, profile)
    growth = await build_growth_center(db_session, profile)

    assert home["peach_view_of_user"]
    assert home["personalized_prompts"] == []
    assert growth["readiness_score"] > 0
    assert growth["stats"]["tracked_issue_count"] >= 1
    assert growth["recommendation"]["title"]


@pytest.mark.asyncio
async def test_home_recommendations_are_cached_and_user_scoped(db_session) -> None:
    profile = UserProfile(
        id="u-recommend-a",
        username="Apple01",
        name="Apple01",
        target_role="AI 产品经理",
        target_company="字节跳动",
        resume_text="负责 AIGC 素材工具，从需求调研到指标设计都有参与，沉淀了项目复盘。",
    )
    other_profile = UserProfile(id="u-recommend-b", username="Banana052", name="Banana052")
    db_session.add_all([profile, other_profile])
    db_session.add(
        GrowthIssue(
            user_id=profile.id,
            issue_key="project_decision_reasoning",
            title="项目决策依据不足",
            description="需要把为什么做、怎么取舍和指标证据说清楚。",
            ability_dimension="project_deep_dive",
            status="new",
        )
    )
    await db_session.commit()

    empty_home = await build_home_context(db_session, other_profile)
    assert empty_home["personalized_prompts"] == []

    refreshed = await refresh_home_recommendations(
        db_session,
        profile,
        trigger_reason="interview_finish",
        source_type="interview",
        source_id="iv-recommend-a",
        force=True,
    )
    await db_session.commit()

    home = await build_home_context(db_session, profile)
    stored = (
        await db_session.execute(select(HomeRecommendation).where(HomeRecommendation.user_id == profile.id))
    ).scalars().all()
    other_stored = (
        await db_session.execute(select(HomeRecommendation).where(HomeRecommendation.user_id == other_profile.id))
    ).scalars().all()

    assert refreshed
    assert home["personalized_prompts"] == [item["text"] for item in refreshed]
    assert any("项目决策依据不足" in item["text"] for item in refreshed)
    assert stored
    assert other_stored == []


def test_recommendation_probability_gate() -> None:
    assert should_refresh_recommendations("u-a", "memory", "m-a", probability=0) is False
    assert should_refresh_recommendations("u-a", "memory", "m-a", probability=1) is True


@pytest.mark.asyncio
async def test_profile_zero_to_one_signal_forces_home_recommendations(db_session) -> None:
    profile = UserProfile(id="u-zero-one", username="Cherry07", name="同学", target_role="产品经理", resume_text="")
    db_session.add(profile)
    await db_session.commit()

    assert has_profile_recommendation_signal(profile) is False
    empty_home = await build_home_context(db_session, profile)
    assert empty_home["personalized_prompts"] == []

    profile.resume_text = (
        "负责 AIGC 广告素材二创工具，从需求调研到上线复盘都有参与，"
        "完成创作者访谈、需求优先级排序、指标设计和灰度复盘，"
        "沉淀了用户痛点、方案取舍、上线结果和可追问项目细节。"
    )
    assert has_profile_recommendation_signal(profile) is True
    refreshed = await refresh_home_recommendations(
        db_session,
        profile,
        trigger_reason="profile",
        source_type="profile",
        source_id=profile.id,
        force=True,
    )

    assert refreshed
    assert any(item["source_type"] == "resume" for item in refreshed)
