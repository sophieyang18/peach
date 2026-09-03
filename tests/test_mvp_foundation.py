from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.app.models import ApplicationState, CandidateProfile, InterviewQuestion, ProductEvent, RewardEvent, UserProfile
from backend.app.services.analytics import record_product_event
from backend.app.services.applications import create_application, list_applications, patch_application
from backend.app.services.candidate_profile import ensure_candidate_profile, serialize_candidate_profile
from backend.app.services.companion import ensure_daily_action, update_daily_action
from backend.app.services.conversations import list_conversations, sync_conversations
from backend.app.services.interview_intelligence import build_question_set, import_experience
from backend.app.services.rewards import refresh_tree_stage, serialize_tree


@pytest.mark.asyncio
async def test_candidate_profile_builds_structured_snapshot_from_resume(db_session) -> None:
    profile = UserProfile(
        id="u-candidate-profile",
        username="peach-candidate",
        name="杨诗卉",
        target_role="AI 产品经理",
        target_company="字节跳动",
        resume_text=(
            "教育背景 北京航空航天大学 外国语言学 GPA 3.86/4.0\n"
            "实习经历 负责 AIGC 广告素材二创工具，从需求调研到 PRD、数据分析和复盘。\n"
            "项目经历 设计 Agent 求职陪练产品，使用 Python、SQL、Figma 和 Axure 完成交互验证。\n"
            "技能 Figma Axure SQL Python Excel"
        ),
    )
    db_session.add(profile)

    candidate = await ensure_candidate_profile(db_session, profile, force=True, source="test")
    await db_session.commit()
    serialized = serialize_candidate_profile(candidate)

    assert serialized["completeness"] >= 60
    assert "Python" in serialized["skills"]
    assert "SQL" in serialized["skills"]
    assert serialized["target_preferences"]["role"] == "AI 产品经理"


@pytest.mark.asyncio
async def test_candidate_profile_keeps_bullets_inside_each_experience(db_session) -> None:
    profile = UserProfile(
        id="u-candidate-experience-chunks",
        username="candidate-experience-chunks",
        name="杨诗卉",
        resume_text=(
            "实习经历\n"
            "字节跳动 - AI产品经理 2026.3-至今 北京\n"
            "• 工作概述：聚焦AIGC广告素材二创链路迭代，通过平台合作实现链路收益。\n"
            "• 链路改造：主导将后验数据注入多模态分析节点。\n"
            "快手 - AI产品经理 2025.10-2026.3 北京\n"
            "• 工作概述：主导3款AI创作工具从0到1落地与迭代。\n"
            "百度 - AIGC策略产品经理 2025.6-2025.9 北京\n"
            "• 工作概述：主导AIGC原生视频自动化链路建设与优化。\n"
            "项目经历\n"
            "减肥搭子Agent项目丨独立产品和研发丨2025.7\n"
        ),
    )
    db_session.add(profile)

    candidate = await ensure_candidate_profile(db_session, profile, force=True, source="test")
    await db_session.commit()

    assert [item["title"] for item in candidate.experiences] == [
        "字节跳动 - AI产品经理 2026.3-至今 北京",
        "快手 - AI产品经理 2025.10-2026.3 北京",
        "百度 - AIGC策略产品经理 2025.6-2025.9 北京",
    ]
    assert "通过平台合作" in candidate.experiences[0]["summary"]


@pytest.mark.asyncio
async def test_candidate_profile_is_user_scoped(db_session) -> None:
    first = UserProfile(id="u-profile-a", username="profile-a", name="A", resume_text="项目经历 负责 AI 产品。")
    second = UserProfile(id="u-profile-b", username="profile-b", name="B", resume_text="项目经历 负责增长产品。")
    db_session.add_all([first, second])

    await ensure_candidate_profile(db_session, first, force=True, source="test")
    await ensure_candidate_profile(db_session, second, force=True, source="test")
    await db_session.commit()

    rows = (await db_session.execute(select(CandidateProfile))).scalars().all()
    assert {row.user_id for row in rows} == {first.id, second.id}


@pytest.mark.asyncio
async def test_product_event_redacts_sensitive_properties(db_session) -> None:
    profile = UserProfile(id="u-event", username="event-user", name="Event")
    db_session.add(profile)
    payload = SimpleNamespace(
        event_name="resume_upload",
        page="profile",
        module="full",
        source="web",
        anonymous_id="anon-1",
        session_id="session-1",
        client_version="mvp-test",
        device_type="desktop",
        browser="chrome",
        referrer="",
        properties={
            "email": "2717316658@qq.com",
            "phone": "15280241298",
            "resume_text": "完整简历正文不应入库",
            "note": "联系我 152-8024-1298",
        },
    )

    await record_product_event(db_session, profile, payload)
    await db_session.commit()
    event = (await db_session.execute(select(ProductEvent))).scalar_one()

    assert event.properties["email"] == "[redacted]"
    assert event.properties["phone"] == "[redacted]"
    assert event.properties["resume_text"] == "[redacted]"
    assert "152" not in event.properties["note"]


@pytest.mark.asyncio
async def test_conversation_sync_recovers_history_and_is_user_scoped(db_session) -> None:
    first = UserProfile(id="u-conv-a", username="conv-a", name="A")
    second = UserProfile(id="u-conv-b", username="conv-b", name="B")
    db_session.add_all([first, second])
    payload = SimpleNamespace(
        activeConversationId="chat-same-client-id",
        conversations=[
            SimpleNamespace(
                id="chat-same-client-id",
                title="AI 产品面试",
                updatedAt="刚刚",
                messages=[
                    SimpleNamespace(role="user", content="帮我模拟面试", actions=[]),
                    SimpleNamespace(role="peach", content="我们先从自我介绍开始。", actions=[]),
                ],
            )
        ],
    )

    await sync_conversations(db_session, first, payload)
    await sync_conversations(db_session, second, SimpleNamespace(activeConversationId="", conversations=[]))
    await db_session.commit()

    first_history = await list_conversations(db_session, first)
    second_history = await list_conversations(db_session, second)

    assert first_history["conversations"][0]["title"] == "AI 产品面试"
    assert first_history["conversations"][0]["messages"][1]["content"] == "我们先从自我介绍开始。"
    assert second_history["conversations"] == []


@pytest.mark.asyncio
async def test_application_state_updates_daily_action_and_rewards(db_session) -> None:
    profile = UserProfile(
        id="u-application",
        username="application-user",
        name="桃子",
        target_role="产品经理",
        target_company="字节跳动",
        resume_text="项目经历 做过 AIGC 内容增长平台，负责需求分析、数据归因和 PRD。",
    )
    db_session.add(profile)

    application = await create_application(
        db_session,
        profile,
        SimpleNamespace(
            company="字节跳动",
            role="产品经理",
            jd_text="负责内容产品增长和策略迭代",
            source_url="https://jobs.example.com/pm",
            resume_version_id="",
            status="ready",
            source="manual",
            notes="需要准备业务一面",
        ),
    )
    await patch_application(db_session, profile, application.id, SimpleNamespace(model_dump=lambda exclude_unset=True: {"status": "interview"}))
    daily = await ensure_daily_action(db_session, profile, force_new=True)
    await update_daily_action(db_session, profile, daily.id, "completed")
    await refresh_tree_stage(db_session, profile)
    await db_session.commit()

    applications = await list_applications(db_session, profile)
    rewards = (await db_session.execute(select(RewardEvent).where(RewardEvent.user_id == profile.id))).scalars().all()

    assert applications["summary"]["interviewing"] == 1
    assert daily.action_type == "target_company_mock"
    assert daily.status == "completed"
    assert {reward.event_type for reward in rewards} >= {"application_completed", "daily_action_completed"}


@pytest.mark.asyncio
async def test_peach_tree_progress_is_user_scoped(db_session) -> None:
    first = UserProfile(id="u-tree-a", username="tree-a", name="A")
    second = UserProfile(id="u-tree-b", username="tree-b", name="B")
    db_session.add_all([first, second])

    first_app = await create_application(
        db_session,
        first,
        SimpleNamespace(company="A 公司", role="产品经理", jd_text="", source_url="", resume_version_id="", status="applied", source="manual", notes=""),
    )
    await create_application(
        db_session,
        second,
        SimpleNamespace(company="B 公司", role="产品经理", jd_text="", source_url="", resume_version_id="", status="ready", source="manual", notes=""),
    )
    first_tree = await refresh_tree_stage(db_session, first)
    second_tree = await refresh_tree_stage(db_session, second)
    await db_session.commit()

    assert first_app.applied_at is not None
    assert serialize_tree(first_tree)["growth_xp"] > serialize_tree(second_tree)["growth_xp"]


@pytest.mark.asyncio
async def test_interview_experience_import_builds_personalized_question_set(db_session) -> None:
    profile = UserProfile(
        id="u-interview-intel",
        username="interview-intel",
        name="杨诗卉",
        target_role="产品经理",
        target_company="字节跳动",
        stage="业务一面",
        resume_text="项目经历 减肥搭子Agent项目，负责需求调研、产品方案和数据复盘。",
    )
    db_session.add(profile)
    payload = SimpleNamespace(
        company="字节跳动",
        role="产品经理",
        department="商业化",
        interview_stage="业务一面",
        interview_date="2026-08",
        raw_content=(
            "面试官：请介绍一个你最有代表性的项目？\n"
            "追问：这个项目里你做过最关键的取舍是什么？\n"
            "问题：如果数据结果不符合预期，你会怎么定位原因？"
        ),
        source_type="manual",
        source_name="面经导入",
        source_url="",
        published_at="",
    )

    experience, questions = await import_experience(db_session, profile, payload)
    question_set = await build_question_set(
        db_session,
        profile,
        SimpleNamespace(company="字节跳动", role="产品经理", interview_stage="业务一面", jd="负责商业化产品策略", limit=6),
    )
    await db_session.commit()

    all_questions = (await db_session.execute(select(InterviewQuestion))).scalars().all()
    assert experience.status == "processed"
    assert len(questions) == 3
    assert len(all_questions) == 3
    assert len(question_set.questions) >= 4
    assert any("减肥搭子Agent项目" in item["question"] for item in question_set.questions)
