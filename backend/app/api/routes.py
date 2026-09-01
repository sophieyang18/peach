import re
from contextvars import ContextVar

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import delete, desc, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.db import SessionLocal, get_session
from backend.app.models import (
    AbilityScoreHistory,
    ActionState,
    AgentMemory,
    AgentMemoryEvent,
    ApplicationState,
    CandidateProfile,
    Conversation,
    ConversationMessage,
    DailyAction,
    GrowthInsight,
    GrowthIssue,
    HomeRecommendation,
    InterviewExperience,
    InterviewQuestion,
    InterviewQuestionSet,
    InterviewSession,
    KnowledgeFolder,
    KnowledgeResource,
    PeachTreeState,
    PracticeRecord,
    ProductEvent,
    RewardEvent,
    ResumeVersion,
    UserAbilityScore,
    UserProfile,
)
from backend.app.schemas import (
    AccountIn,
    AgentActionIn,
    AgentToolExecuteIn,
    ApplicationIn,
    ApplicationPatchIn,
    CandidateProfilePatchIn,
    ChatIn,
    ConversationSyncIn,
    DailyActionPatchIn,
    InterviewExperienceIn,
    InterviewAnswerIn,
    InterviewStartIn,
    KnowledgeFolderIn,
    KnowledgeIn,
    KnowledgeLinkIn,
    PracticeIn,
    ProductEventIn,
    ProfileIn,
    QuestionSetBuildIn,
    ReviewIn,
)
from backend.app.services.analytics import analytics_summary, record_product_event
from backend.app.services.agent import PeachAgent
from backend.app.services.applications import create_application, delete_application, list_applications, patch_application, serialize_application
from backend.app.services.candidate_profile import ensure_candidate_profile, serialize_candidate_profile
from backend.app.services.companion import build_job_weather, ensure_daily_action, serialize_daily_action, update_daily_action
from backend.app.services.conversations import delete_conversation, list_conversations, sync_conversations
from backend.app.services.file_parser import SUPPORTED_EXTENSIONS, parse_link, parse_upload
from backend.app.services.growth import apply_interview_growth_update, build_growth_center, build_home_context
from backend.app.services.interview_intelligence import (
    build_question_set,
    import_experience,
    serialize_experience,
    serialize_question,
    serialize_question_set,
)
from backend.app.services.memory import PeachMemoryService, build_memory_context, remember_interaction, remember_interaction_isolated, retrieve_relevant_memories, upsert_memory
from backend.app.services.recommendations import refresh_home_recommendations
from backend.app.services.rewards import award_once, ensure_tree, refresh_tree_stage, serialize_tree

router = APIRouter(prefix="/api")
agent = PeachAgent()
current_username: ContextVar[str] = ContextVar("peach_current_username", default="demo")
USERNAME_MAX_LENGTH = 40
MIN_INTERVIEW_ANSWERS_FOR_LLM_FINISH = 8
TARGET_INTERVIEW_ANSWERS = 10
MAX_INTERVIEW_ANSWERS = 12
INTERVIEW_CHECKLIST = [
    ("self_intro", "自我介绍", "开场介绍已经建立候选人背景和目标"),
    ("experience_deep_dive", "经历深挖", "至少追问过一段实习或项目的背景、行动和结果"),
    ("role_understanding", "岗位理解", "覆盖了对岗位、公司、用户或业务的理解"),
    ("evidence_quality", "证据质量", "回答中出现可验证的贡献、指标、结果或事实边界"),
    ("pressure_followup", "压力追问", "完成过质疑、挑战或反事实追问"),
    ("closing_readiness", "收尾准备", "已经足够生成可执行复盘和下一步计划"),
]


def normalize_username(value: str | None, fallback: str = "demo") -> str:
    username = (value or "").strip()
    if not username:
        username = fallback
    return username[:USERNAME_MAX_LENGTH]


def require_username(value: str | None) -> str:
    username = normalize_username(value, fallback="")
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    return username


def has_profile_recommendation_signal(profile: UserProfile) -> bool:
    """Whether the profile has user-provided material worth refreshing home prompts for."""
    return any(
        [
            bool((profile.resume_text or "").strip()),
            bool((profile.target_company or "").strip()),
            bool((profile.target_city or "").strip()),
            bool((profile.name or "").strip() and profile.name != "同学"),
            bool((profile.target_role or "").strip() and profile.target_role != "产品经理"),
        ]
    )


async def get_existing_profile(session: AsyncSession, username: str) -> UserProfile | None:
    result = await session.execute(select(UserProfile).where(UserProfile.username == username).limit(1))
    return result.scalar_one_or_none()


async def get_or_create_profile(session: AsyncSession, username: str | None = None) -> UserProfile:
    resolved_username = normalize_username(username or current_username.get())
    result = await session.execute(select(UserProfile).where(UserProfile.username == resolved_username).limit(1))
    profile = result.scalar_one_or_none()
    if profile:
        return profile

    profile = UserProfile(
        username=resolved_username,
        name="同学",
        target_role="产品经理",
        stage="投递期",
        resume_text="",
        communication_style="温暖直接",
        strengths=["目标岗位聚焦", "愿意持续练习"],
        weak_points=["回答结构需要稳定", "简历亮点需要量化"],
        plan=default_plan(),
    )
    session.add(profile)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_existing_profile(session, resolved_username)
        if existing:
            return existing
        raise
    await session.refresh(profile)
    return profile


async def remember_interaction_safely(
    session: AsyncSession,
    agent: PeachAgent,
    profile: UserProfile,
    *,
    source: str,
    user_message: str,
    assistant_reply: str,
    context: dict,
) -> list[AgentMemory]:
    return await remember_interaction_isolated(
        agent,
        user_id=profile.id,
        username=profile.username,
        profile_snapshot=profile_snapshot(profile),
        source=source,
        user_message=user_message,
        assistant_reply=assistant_reply,
        context=context,
    )


def profile_snapshot(profile: UserProfile) -> dict:
    return {
        "name": profile.name,
        "target_role": profile.target_role,
        "target_company": profile.target_company,
        "target_city": profile.target_city,
        "stage": profile.stage,
        "resume_text": profile.resume_text,
        "communication_style": profile.communication_style,
        "strengths": list(profile.strengths or []),
        "weak_points": list(profile.weak_points or []),
        "plan": list(profile.plan or []),
    }


@router.post("/accounts/login")
async def login_account(payload: AccountIn, session: AsyncSession = Depends(get_session)) -> dict:
    username = require_username(payload.username)
    profile = await get_existing_profile(session, username)
    if not profile:
        raise HTTPException(status_code=404, detail="账号不存在，可以直接创建这个账号")
    return {"account": serialize_account(profile), "profile": serialize_profile(profile)}


@router.post("/accounts")
async def create_account(payload: AccountIn, session: AsyncSession = Depends(get_session)) -> dict:
    username = require_username(payload.username)
    profile = await get_existing_profile(session, username)
    if not profile:
        profile = await get_or_create_profile(session, username)
        await ensure_default_folders(session, profile.id)
    return {"account": serialize_account(profile), "profile": serialize_profile(profile)}


@router.post("/accounts/reset")
async def reset_account(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    await session.execute(delete(PracticeRecord).where(PracticeRecord.user_id == profile.id))
    await session.execute(delete(InterviewSession).where(InterviewSession.user_id == profile.id))
    await session.execute(delete(KnowledgeResource).where(KnowledgeResource.user_id == profile.id))
    await session.execute(delete(KnowledgeFolder).where(KnowledgeFolder.user_id == profile.id))
    await session.execute(delete(ResumeVersion).where(ResumeVersion.user_id == profile.id))
    await session.execute(delete(CandidateProfile).where(CandidateProfile.user_id == profile.id))
    await session.execute(delete(ConversationMessage).where(ConversationMessage.user_id == profile.id))
    await session.execute(delete(Conversation).where(Conversation.user_id == profile.id))
    await session.execute(delete(ProductEvent).where(ProductEvent.user_id == profile.id))
    await session.execute(delete(ApplicationState).where(ApplicationState.user_id == profile.id))
    await session.execute(delete(DailyAction).where(DailyAction.user_id == profile.id))
    await session.execute(delete(PeachTreeState).where(PeachTreeState.user_id == profile.id))
    await session.execute(delete(RewardEvent).where(RewardEvent.user_id == profile.id))
    await session.execute(delete(InterviewExperience).where(InterviewExperience.user_id == profile.id))
    await session.execute(delete(InterviewQuestionSet).where(InterviewQuestionSet.user_id == profile.id))
    await session.execute(delete(ActionState).where(ActionState.user_id == profile.id))
    await session.execute(delete(AbilityScoreHistory).where(AbilityScoreHistory.user_id == profile.id))
    await session.execute(delete(UserAbilityScore).where(UserAbilityScore.user_id == profile.id))
    await session.execute(delete(GrowthInsight).where(GrowthInsight.user_id == profile.id))
    await session.execute(delete(GrowthIssue).where(GrowthIssue.user_id == profile.id))
    await session.execute(delete(HomeRecommendation).where(HomeRecommendation.user_id == profile.id))
    await session.execute(delete(AgentMemoryEvent).where(AgentMemoryEvent.user_id == profile.id))
    await session.execute(delete(AgentMemory).where(AgentMemory.user_id == profile.id))
    profile.name = "同学"
    profile.target_role = "产品经理"
    profile.target_company = ""
    profile.target_city = ""
    profile.stage = "投递期"
    profile.resume_text = ""
    profile.communication_style = "温暖直接"
    profile.strengths = ["目标岗位聚焦", "愿意持续练习"]
    profile.weak_points = ["回答结构需要稳定", "简历亮点需要量化"]
    profile.plan = default_plan()
    await session.commit()
    await session.refresh(profile)
    await ensure_default_folders(session, profile.id)
    return {"account": serialize_account(profile), "profile": serialize_profile(profile)}


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "peach-agent"}


@router.get("/health/deep")
async def deep_health(session: AsyncSession = Depends(get_session)) -> dict:
    settings = get_settings()
    checks: dict[str, dict] = {}

    try:
        await session.execute(text("select 1"))
        checks["database"] = {"ok": True, "detail": "database reachable"}
    except Exception as exc:
        checks["database"] = {"ok": False, "detail": str(exc)[:240]}

    checks["llm"] = {
        "ok": bool(settings.deepseek_api_key),
        "provider": "deepseek-openai-compatible",
        "model": settings.deepseek_model,
        "base_url": settings.deepseek_base_url,
        "detail": "api key configured" if settings.deepseek_api_key else "api key missing, LLM chat unavailable",
    }
    checks["file_parser"] = {
        "ok": True,
        "formats": sorted(SUPPORTED_EXTENSIONS),
        "max_upload_mb": 12,
    }
    checks["agent_memory"] = {
        "ok": True,
        "scope": "per-user profile id",
        "retrieval_limit": 5,
        "max_user_memories": 80,
    }
    checks["runtime"] = {
        "ok": True,
        "app_env": settings.app_env,
        "cors_origins": settings.cors_origins,
    }

    ok = checks["database"]["ok"] and checks["file_parser"]["ok"]
    return {
        "status": "ok" if ok else "degraded",
        "service": "peach-agent",
        "checks": checks,
    }


@router.get("/capabilities")
async def capabilities() -> dict:
    return {
        "name": "桃子求职陪练 Agent",
        "core_agentic_flows": [
            "LLM 对话规划并提出需用户审批的工具动作",
            "沉浸式语音模拟面试，支持 Web Speech 识别和浏览器 TTS",
            "模拟面试结束后生成结构化复盘报告并归档到个人档案",
            "个人档案、完整简历、实习/项目/教育/技能经历沉淀",
            "个人知识库文件上传、链接解析、资料编辑和基于知识库问答",
            "长期记忆按用户隔离检索，让 Agent 越用越了解用户",
            "投递状态、每日行动和成长奖励闭环，辅助用户判断下一步",
            "面经导入、问题抽取和个性化题集生成，支持更贴近真实面试的训练",
        ],
        "tools": [
            "start_interview",
            "finish_latest_interview",
            "update_profile_fields",
            "update_resume",
            "append_profile_note",
            "add_knowledge_item",
            "update_knowledge_item",
            "delete_knowledge_item",
            "create_application",
            "update_application_status",
            "complete_daily_action",
            "import_interview_experience",
            "build_interview_question_set",
        ],
        "file_formats": sorted(SUPPORTED_EXTENSIONS),
        "safety": [
            "工具动作默认需要用户确认",
            "进行中的面试会锁定导航，防止误切功能丢失上下文",
            "账号 demo 使用用户名隔离数据和记忆",
        ],
    }


@router.get("/profile")
async def read_profile(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    return serialize_profile(profile)


@router.get("/profile/export")
async def export_profile(format: str = "md", session: AsyncSession = Depends(get_session)) -> Response:
    profile = await get_or_create_profile(session)
    content = profile_export_content(profile)
    return downloadable_text_response(content, f"peach-profile-{profile.username}", format)


@router.get("/candidate-profile")
async def read_candidate_profile(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    candidate = await ensure_candidate_profile(session, profile)
    await session.commit()
    await session.refresh(candidate)
    return {"candidate_profile": serialize_candidate_profile(candidate)}


@router.post("/candidate-profile/initialize")
async def initialize_candidate_profile(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    candidate = await ensure_candidate_profile(session, profile, force=True, source="initialize")
    await session.commit()
    await session.refresh(candidate)
    return {"candidate_profile": serialize_candidate_profile(candidate)}


@router.patch("/candidate-profile")
async def update_candidate_profile(payload: CandidateProfilePatchIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    candidate = await ensure_candidate_profile(session, profile)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(candidate, key, value)
    candidate.completeness = candidate_profile_completeness(candidate.field_statuses)
    candidate.source = "user_confirmed"
    await session.commit()
    await session.refresh(candidate)
    return {"candidate_profile": serialize_candidate_profile(candidate)}


@router.get("/conversations")
async def read_conversations(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    return await list_conversations(session, profile)


@router.post("/conversations/sync")
async def sync_user_conversations(payload: ConversationSyncIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    result = await sync_conversations(session, profile, payload)
    await session.commit()
    return result


@router.delete("/conversations/{conversation_id}")
async def delete_user_conversation(conversation_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    deleted = await delete_conversation(session, profile, conversation_id)
    await session.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"deleted": True, "id": conversation_id}


@router.post("/events")
async def track_product_event(payload: ProductEventIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    event = await record_product_event(session, profile, payload)
    await session.commit()
    return {"ok": True, "event_id": event.id}


@router.get("/analytics/summary")
async def read_analytics_summary(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    return await analytics_summary(session, profile.id)


@router.get("/applications")
async def read_applications(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    return await list_applications(session, profile)


@router.post("/applications")
async def create_application_state(payload: ApplicationIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    item = await create_application(session, profile, payload)
    daily = await ensure_daily_action(session, profile, force_new=True)
    tree = await refresh_tree_stage(session, profile)
    await session.commit()
    await session.refresh(item)
    return {
        "application": serialize_application(item),
        "daily_action": serialize_daily_action(daily),
        "job_weather": await build_job_weather(session, profile),
        "peach_tree": serialize_tree(tree),
    }


@router.patch("/applications/{application_id}")
async def update_application_state(application_id: str, payload: ApplicationPatchIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    item = await patch_application(session, profile, application_id, payload)
    daily = await ensure_daily_action(session, profile, force_new=True)
    tree = await refresh_tree_stage(session, profile)
    await session.commit()
    await session.refresh(item)
    return {
        "application": serialize_application(item),
        "daily_action": serialize_daily_action(daily),
        "job_weather": await build_job_weather(session, profile),
        "peach_tree": serialize_tree(tree),
    }


@router.delete("/applications/{application_id}")
async def delete_application_state(application_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    await delete_application(session, profile, application_id)
    tree = await refresh_tree_stage(session, profile)
    await session.commit()
    return {"deleted": True, "id": application_id, "peach_tree": serialize_tree(tree)}


@router.get("/job-weather")
async def read_job_weather(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    return {"job_weather": await build_job_weather(session, profile)}


@router.get("/daily-action")
async def read_daily_action(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    action = await ensure_daily_action(session, profile)
    await session.commit()
    await session.refresh(action)
    return {"daily_action": serialize_daily_action(action)}


@router.patch("/daily-action/{action_id}")
async def patch_daily_action(action_id: str, payload: DailyActionPatchIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    action = await update_daily_action(session, profile, action_id, payload.status)
    tree = await refresh_tree_stage(session, profile)
    await session.commit()
    await session.refresh(action)
    return {"daily_action": serialize_daily_action(action), "peach_tree": serialize_tree(tree)}


@router.get("/peach-tree")
async def read_peach_tree(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    tree = await refresh_tree_stage(session, profile)
    await session.commit()
    await session.refresh(tree)
    return {"peach_tree": serialize_tree(tree)}


@router.post("/interview-experiences/import")
async def import_interview_experience(payload: InterviewExperienceIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    experience, questions = await import_experience(session, profile, payload)
    await session.commit()
    await session.refresh(experience)
    return {
        "experience": serialize_experience(experience),
        "questions": [serialize_question(item) for item in questions],
    }


@router.get("/interview-experiences")
async def read_interview_experiences(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    items = (
        await session.execute(
            select(InterviewExperience)
            .where(InterviewExperience.user_id == profile.id)
            .order_by(desc(InterviewExperience.imported_at))
            .limit(80)
        )
    ).scalars().all()
    return {"items": [serialize_experience(item) for item in items]}


@router.get("/interview-questions")
async def read_interview_questions(company: str = "", role: str = "", stage: str = "", session: AsyncSession = Depends(get_session)) -> dict:
    query = select(InterviewQuestion)
    if company:
        query = query.where(InterviewQuestion.company == company)
    if role:
        query = query.where(InterviewQuestion.role == role)
    if stage:
        query = query.where(InterviewQuestion.interview_stage == stage)
    items = (await session.execute(query.order_by(desc(InterviewQuestion.source_count)).limit(80))).scalars().all()
    return {"items": [serialize_question(item) for item in items]}


@router.post("/interview-question-set/build")
async def create_interview_question_set(payload: QuestionSetBuildIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    question_set = await build_question_set(session, profile, payload)
    await session.commit()
    await session.refresh(question_set)
    return {"question_set": serialize_question_set(question_set)}


@router.get("/interview-question-set/{question_set_id}")
async def read_interview_question_set(question_set_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    question_set = await session.get(InterviewQuestionSet, question_set_id)
    if not question_set or question_set.user_id != profile.id:
        raise HTTPException(status_code=404, detail="question set not found")
    return {"question_set": serialize_question_set(question_set)}


@router.get("/profile/resumes")
async def list_resume_versions(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    return {"items": await serialized_resume_versions(session, profile.id)}


@router.post("/profile/resumes/upload")
async def upload_resume_version(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    parsed = await parse_uploaded_file(file)
    was_resume_empty = not (profile.resume_text or "").strip()
    version = await create_resume_version(
        session,
        profile,
        parsed["content"],
        title=parsed["title"] or parsed["filename"],
        filename=parsed["filename"],
        source="upload",
        optimized=0,
    )
    if was_resume_empty:
        profile.resume_text = parsed["content"]
    candidate = await ensure_candidate_profile(session, profile, force=True, source="resume_upload")
    await award_once(session, profile, "first_resume_uploaded", version.id if version else profile.id, {"filename": parsed["filename"]})
    if (candidate.completeness or 0) >= 55:
        await award_once(session, profile, "profile_completed", candidate.id, {"completeness": candidate.completeness})
    await refresh_recommendations_safely(
        session,
        profile,
        trigger_reason="resume",
        source_type="resume",
        source_id=version.id if version else profile.id,
        force=was_resume_empty,
    )
    await session.commit()
    await session.refresh(profile)
    return {
        "file": parsed,
        "resume_version": serialize_resume_version(version) if version else None,
        "resume_versions": await serialized_resume_versions(session, profile.id),
        "profile": serialize_profile(profile),
    }


@router.get("/profile/resumes/{resume_id}/export")
async def export_resume_version(resume_id: str, format: str = "md", session: AsyncSession = Depends(get_session)) -> Response:
    profile = await get_or_create_profile(session)
    resume = await owned_resume_version(session, profile.id, resume_id)
    title = resume.title or resume.filename or "完整简历"
    content = f"# {title}\n\n{resume.content.strip()}\n"
    return downloadable_text_response(content, f"peach-resume-v{resume.version_no}", format)


@router.post("/profile/resumes/{resume_id}/restore")
async def restore_resume_version(resume_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    resume = await owned_resume_version(session, profile.id, resume_id)
    profile.resume_text = resume.content
    await session.commit()
    await session.refresh(profile)
    return {"profile": serialize_profile(profile), "resume_version": serialize_resume_version(resume)}


@router.post("/profile")
async def upsert_profile(payload: ProfileIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    had_recommendation_signal = has_profile_recommendation_signal(profile)
    previous_resume_text = profile.resume_text or ""
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)

    has_recommendation_signal = has_profile_recommendation_signal(profile)
    force_recommendations = not had_recommendation_signal and has_recommendation_signal
    if (profile.resume_text or "").strip():
        profile.strengths = merge_points(profile.strengths, ["已有可用于面试和简历生成的材料"])
        profile.weak_points = merge_points(profile.weak_points, ["简历亮点需要继续量化和证据化"])
    if not profile.plan:
        profile.plan = default_plan()
    await refresh_recommendations_safely(
        session,
        profile,
        trigger_reason="profile",
        source_type="profile",
        source_id=profile.id,
        force=force_recommendations,
    )
    resume_version = None
    if (profile.resume_text or "").strip() and normalize_for_compare(previous_resume_text) != normalize_for_compare(profile.resume_text):
        resume_version = await create_resume_version(
            session,
            profile,
            profile.resume_text,
            title="手动保存完整简历",
            source="profile_save",
            optimized=1 if "优化" in profile.resume_text else 0,
        )
        candidate = await ensure_candidate_profile(session, profile, force=True, source="profile_save")
        if (candidate.completeness or 0) >= 55:
            await award_once(session, profile, "profile_completed", candidate.id, {"completeness": candidate.completeness})
    await session.commit()
    await session.refresh(profile)
    return {
        "profile": serialize_profile(profile),
        "greeting": "个人档案已保存。",
        "resume_version": serialize_resume_version(resume_version) if resume_version else None,
        "resume_versions": await serialized_resume_versions(session, profile.id),
    }


@router.get("/dashboard")
async def dashboard(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    records = (
        await session.execute(
            select(PracticeRecord)
            .where(PracticeRecord.user_id == profile.id)
            .order_by(desc(PracticeRecord.created_at))
            .limit(5)
        )
    ).scalars().all()
    interviews = (
        await session.execute(
            select(InterviewSession)
            .where(InterviewSession.user_id == profile.id)
            .order_by(desc(InterviewSession.created_at))
            .limit(5)
        )
    ).scalars().all()
    checkin = build_local_checkin(profile, list(records))
    home_context = await build_home_context(session, profile)
    growth_center = await build_growth_center(session, profile)
    candidate = await ensure_candidate_profile(session, profile)
    applications = await list_applications(session, profile)
    daily = await ensure_daily_action(session, profile)
    tree = await refresh_tree_stage(session, profile)
    await session.commit()
    await session.refresh(candidate)
    await session.refresh(daily)
    await session.refresh(tree)

    return {
        "profile": serialize_profile(profile),
        "candidate_profile": serialize_candidate_profile(candidate),
        "applications": applications["items"],
        "application_summary": applications["summary"],
        "job_weather": await build_job_weather(session, profile),
        "daily_action": serialize_daily_action(daily),
        "peach_tree": serialize_tree(tree),
        "resume_versions": await serialized_resume_versions(session, profile.id),
        "checkin": checkin,
        "recent_practices": [serialize_practice(item) for item in records],
        "recent_interviews": [serialize_interview(item) for item in interviews],
        "memories": [serialize_memory(item) for item in await list_recent_memories(session, profile.id, 8)],
        "growth": build_growth(profile, list(records), list(interviews)),
        "home_context": home_context,
        "growth_center": growth_center,
    }


@router.get("/home-context")
async def home_context(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    return await build_home_context(session, profile)


@router.get("/growth")
async def growth_center(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    return await build_growth_center(session, profile)


@router.get("/memories")
async def list_memories(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    memories = await list_recent_memories(session, profile.id, 80)
    return {"items": [serialize_memory(item) for item in memories]}


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    deleted = await PeachMemoryService(session).delete(memory_id, user_id=profile.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="memory not found")
    await session.commit()
    return {"deleted": True, "id": memory_id}


@router.post("/practice")
async def submit_practice(payload: PracticeIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    memory_context = await relevant_memory_context(session, profile, f"{payload.question}\n{payload.answer}", task_type="growth_analysis")
    feedback = await agent.evaluate_practice(profile, payload.question, payload.answer, memory_context)
    record = PracticeRecord(
        user_id=profile.id,
        question=payload.question,
        answer=payload.answer,
        feedback=feedback,
        score=int(feedback.get("score", 0)),
        tags=payload.tags,
    )
    profile.weak_points = merge_points(profile.weak_points, feedback.get("improvements", []))
    profile.strengths = merge_points(profile.strengths, feedback.get("highlights", []))
    session.add(record)
    await session.flush()
    await refresh_recommendations_safely(session, profile, trigger_reason="practice", source_type="practice", source_id=record.id)
    await session.commit()
    await session.refresh(record)
    await remember_interaction_safely(
        session,
        agent,
        profile,
        source="practice",
        user_message=f"题目：{payload.question}\n回答：{payload.answer}",
        assistant_reply=str(feedback),
        context={"memory_context_used": memory_context, "tags": payload.tags},
    )
    return {"record": serialize_practice(record), "feedback": feedback}


@router.post("/interviews")
async def start_interview(payload: InterviewStartIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    question_set_context = ""
    if payload.question_set_id:
        question_set = await session.get(InterviewQuestionSet, payload.question_set_id)
        if not question_set or question_set.user_id != profile.id:
            raise HTTPException(status_code=404, detail="question set not found")
        question_set_context = "\n".join(
            f"{index + 1}. {item.get('question', '')}（来源：{item.get('source_type', 'unknown')}，考察点：{item.get('assessment_point', '')}）"
            for index, item in enumerate((question_set.questions or [])[:10])
        )
    memory_context = await relevant_memory_context(
        session,
        profile,
        "\n".join([payload.company, payload.role, payload.jd, payload.question_bank, question_set_context]),
        task_type="mock_interview",
    )
    interview = InterviewSession(
        user_id=profile.id,
        interview_type=payload.interview_type,
        interviewer_style=payload.interviewer_style,
        company=payload.company or profile.target_company,
        role=payload.role or profile.target_role,
    )
    opening = await agent.start_interview(
        profile,
        interview,
        {
            "jd": payload.jd,
            "question_bank": "\n\n".join([payload.question_bank, question_set_context]).strip(),
            "question_set_id": payload.question_set_id,
            "memory_context": memory_context,
        },
    )
    interview.transcript = [
        *(
            [{"role": "system", "content": f"岗位 JD：{payload.jd[:3000]}"}]
            if payload.jd.strip()
            else []
        ),
        *(
            [{"role": "system", "content": f"题库材料：{payload.question_bank[:3000]}"}]
            if payload.question_bank.strip()
            else []
        ),
        *(
            [{"role": "system", "content": f"个性化题集：{question_set_context[:3000]}"}]
            if question_set_context
            else []
        ),
        {"role": "interviewer", "content": opening["opening"]},
        {"role": "interviewer", "content": opening["question"]},
    ]
    session.add(interview)
    await session.commit()
    await session.refresh(interview)
    await remember_interaction_safely(
        session,
        agent,
        profile,
        source="interview_start",
        user_message=f"开始{payload.interview_type}：{payload.company} {payload.role}\nJD：{payload.jd[:1200]}",
        assistant_reply="\n".join([opening["opening"], opening["question"]]),
        context={
            "interview_id": interview.id,
            "company": interview.company,
            "role": interview.role,
            "interviewer_style": payload.interviewer_style,
            "question_bank": payload.question_bank[:1200],
        },
    )
    return {"interview": serialize_interview(interview), "opening": opening, "progress": build_interview_progress(interview)}


@router.post("/interviews/{interview_id}/answer")
async def answer_interview(
    interview_id: str,
    payload: InterviewAnswerIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    profile = await get_or_create_profile(session)
    interview = await owned_interview(session, profile.id, interview_id)

    memory_context = await relevant_memory_context(session, profile, f"{interview.company} {interview.role}\n{payload.answer}", task_type="mock_interview")
    transcript = [*interview.transcript, {"role": "candidate", "content": payload.answer}]
    interview.transcript = transcript
    next_turn = await agent.continue_interview(profile, interview, payload.answer, memory_context)
    interview.transcript = [
        *interview.transcript,
        {"role": "interviewer", "content": next_turn["micro_feedback"]},
        {"role": "interviewer", "content": next_turn["next_question"]},
    ]

    progress = build_interview_progress(interview)
    llm_can_finish = progress["can_llm_finish"]
    should_offer_finish = bool(next_turn.get("should_finish")) and llm_can_finish
    force_finish = progress["answer_count"] >= MAX_INTERVIEW_ANSWERS
    growth_update = None
    next_turn["should_finish"] = should_offer_finish

    if force_finish:
        interview.status = "completed"
        interview.report = await agent.interview_report(profile, interview, memory_context)
        growth_update = await apply_interview_growth_update(session, profile, interview)
        await award_once(session, profile, "mock_completed", interview.id, {"company": interview.company, "role": interview.role})
        await refresh_recommendations_safely(
            session,
            profile,
            trigger_reason="interview_finish",
            source_type="interview",
            source_id=interview.id,
            force=True,
        )
        progress = build_interview_progress(interview)

    await session.commit()
    await session.refresh(interview)
    await remember_interaction_safely(
        session,
        agent,
        profile,
        source="interview_answer",
        user_message=payload.answer,
        assistant_reply="\n".join([str(next_turn.get("micro_feedback") or ""), str(next_turn.get("next_question") or "")]),
        context={
            "interview_id": interview.id,
            "company": interview.company,
            "role": interview.role,
            "interviewer_style": interview.interviewer_style,
            "progress": progress,
        },
    )
    return {
        "interview": serialize_interview(interview),
        "next": next_turn,
        "report": interview.report,
        "progress": progress,
        "growth_update": serialize_growth_update(growth_update),
        "memory_updates": growth_update.memory_updates if growth_update else [],
        "next_actions": growth_update.actions if growth_update else [],
    }


@router.post("/interviews/{interview_id}/finish")
async def finish_interview(interview_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    interview = await owned_interview(session, profile.id, interview_id)

    memory_context = await relevant_memory_context(session, profile, f"{interview.company} {interview.role}\n{interview.transcript[-8:]}", task_type="growth_analysis")
    interview.status = "completed"
    interview.report = await agent.interview_report(profile, interview, memory_context)
    growth_update = await apply_interview_growth_update(session, profile, interview)
    await award_once(session, profile, "mock_completed", interview.id, {"company": interview.company, "role": interview.role})
    await refresh_recommendations_safely(
        session,
        profile,
        trigger_reason="interview_finish",
        source_type="interview",
        source_id=interview.id,
        force=True,
    )
    await session.commit()
    await session.refresh(interview)
    await remember_interaction_safely(
        session,
        agent,
        profile,
        source="interview_report",
        user_message=f"结束面试：{interview.company} {interview.role}",
        assistant_reply=str(interview.report),
        context={
            "interview_id": interview.id,
            "company": interview.company,
            "role": interview.role,
            "transcript_tail": interview.transcript[-8:],
        },
    )
    return {
        "interview": serialize_interview(interview),
        "report": interview.report,
        "progress": build_interview_progress(interview),
        "growth_update": serialize_growth_update(growth_update),
        "memory_updates": growth_update.memory_updates,
        "next_actions": growth_update.actions,
    }


@router.delete("/interviews/{interview_id}")
async def delete_interview(interview_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    interview = await session.get(InterviewSession, interview_id)
    if not interview or interview.user_id != profile.id:
        raise HTTPException(status_code=404, detail="interview not found")

    await cleanup_interview_related_data(session, profile.id, interview)
    await session.delete(interview)
    await session.commit()
    return {"deleted": True, "id": interview_id}


@router.post("/review")
async def review(payload: ReviewIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    memory_context = await relevant_memory_context(session, profile, str(payload.model_dump()), task_type="growth_analysis")
    feedback = await agent.post_interview_review(profile, payload.model_dump(), memory_context)
    record = PracticeRecord(
        user_id=profile.id,
        question=f"{payload.company or profile.target_company} 面试后复盘",
        answer=f"感受：{payload.feeling}\n问题：{payload.questions}\n反思：{payload.reflection}",
        feedback=feedback,
        score=0,
        tags=["面试复盘"],
    )
    profile.weak_points = merge_points(profile.weak_points, feedback.get("to_improve", []))
    session.add(record)
    await session.flush()
    await refresh_recommendations_safely(session, profile, trigger_reason="review", source_type="practice", source_id=record.id)
    await session.commit()
    await session.refresh(record)
    memory_writes = await remember_interaction_safely(
        session,
        agent,
        profile,
        source="post_interview_review",
        user_message=str(payload.model_dump()),
        assistant_reply=str(feedback),
        context={},
    )
    return {"review": feedback, "record": serialize_practice(record)}


@router.post("/chat")
async def chat(payload: ChatIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    memory_context = await relevant_memory_context(session, profile, payload.message)
    try:
        reply = await agent.chat(profile, payload.message, memory_context)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="LLM 暂时没有返回结果，请稍后重试。") from exc
    memory_writes = await remember_interaction_safely(
        session,
        agent,
        profile,
        source="chat",
        user_message=payload.message,
        assistant_reply=reply,
        context={"memory_context_used": memory_context},
    )
    try:
        if memory_writes:
            await refresh_recommendations_safely(
                session,
                profile,
                trigger_reason="memory",
                source_type="chat",
                source_id=memory_writes[0].id,
            )
        await session.commit()
    except Exception:
        await session.rollback()
    return {"reply": reply, "memory_writes": [serialize_memory(item) for item in memory_writes]}


@router.post("/agent/actions")
async def agent_actions(payload: AgentActionIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    memory_context = await relevant_memory_context(session, profile, payload.message)
    try:
        planned = await agent.plan_actions(profile, payload.message, payload.context, memory_context)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="LLM 暂时没有返回结果，请稍后重试。") from exc
    memory_writes = await remember_interaction_safely(
        session,
        agent,
        profile,
        source="agent_actions",
        user_message=payload.message,
        assistant_reply=str(planned.get("reply", "")),
        context={**payload.context, "memory_context_used": memory_context},
    )
    try:
        if memory_writes:
            await refresh_recommendations_safely(
                session,
                profile,
                trigger_reason="memory",
                source_type="agent_actions",
                source_id=memory_writes[0].id,
            )
        await session.commit()
    except Exception:
        await session.rollback()
    return {
        "reply": planned.get("reply", ""),
        "actions": normalize_tool_actions_safely(planned.get("actions", [])),
        "memory_writes": [serialize_memory(item) for item in memory_writes],
    }


@router.post("/agent/actions/execute")
async def execute_agent_action(payload: AgentToolExecuteIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    data = payload.payload or {}

    if payload.tool == "start_interview":
        interview_payload = InterviewStartIn(
            interview_type=str(data.get("interview_type") or "模拟面试"),
            interviewer_style=str(data.get("interviewer_style") or "不限"),
            company=str(data.get("company") or profile.target_company or ""),
            role=str(data.get("role") or profile.target_role),
            jd=str(data.get("jd") or ""),
            question_bank=str(data.get("question_bank") or ""),
        )
        result = await start_interview(interview_payload, session)
        return {"message": "已创建模拟面试。", **result}

    if payload.tool == "finish_latest_interview":
        interview_id = str(data.get("interview_id") or "").strip()
        interview = await owned_interview(session, profile.id, interview_id) if interview_id else None
        if not interview:
            interview = await latest_interview(session, profile.id, active_only=True)
        if not interview:
            interview = await latest_interview(session, profile.id, active_only=False)
        if not interview:
            raise HTTPException(status_code=404, detail="没有可结束的面试")
        result = await finish_interview(interview.id, session)
        return {"message": "面试已结束，报告已生成。", **result}

    if payload.tool == "update_profile_fields":
        fields = data.get("fields", data)
        if not isinstance(fields, dict):
            raise HTTPException(status_code=400, detail="fields must be an object")
        had_recommendation_signal = has_profile_recommendation_signal(profile)
        allowed = {"name", "target_role", "target_company", "target_city", "stage", "communication_style"}
        for key, value in fields.items():
            if key in allowed:
                setattr(profile, key, str(value))
        force_recommendations = not had_recommendation_signal and has_profile_recommendation_signal(profile)
        await session.commit()
        await session.refresh(profile)
        await remember_approved_action(profile, payload.tool, data, "个人信息已更新。")
        await refresh_recommendations_after_commit(
            profile,
            trigger_reason="profile",
            source_type="profile",
            source_id=profile.id,
            force=force_recommendations,
        )
        return {"message": "个人信息已更新。", "profile": serialize_profile(profile)}

    if payload.tool == "update_resume":
        content = str(data.get("content") or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        mode = str(data.get("mode") or "append")
        was_resume_empty = not (profile.resume_text or "").strip()
        profile.resume_text = content if mode == "replace" else "\n\n".join([item for item in [profile.resume_text, content] if item])
        resume_version = await create_resume_version(
            session,
            profile,
            profile.resume_text,
            title=str(data.get("title") or "AI 更新完整简历"),
            source="agent_update",
            optimized=1,
        )
        await ensure_candidate_profile(session, profile, force=True, source="agent_update")
        await session.commit()
        await session.refresh(profile)
        await remember_approved_action(profile, payload.tool, data, "简历已更新。")
        await refresh_recommendations_after_commit(
            profile,
            trigger_reason="resume",
            source_type="resume",
            source_id=profile.id,
            force=was_resume_empty,
        )
        return {
            "message": "简历已更新。",
            "profile": serialize_profile(profile),
            "resume_version": serialize_resume_version(resume_version) if resume_version else None,
            "resume_versions": await serialized_resume_versions(session, profile.id),
        }

    if payload.tool == "append_profile_note":
        content = str(data.get("content") or "").strip()
        title = str(data.get("title") or "个人档案")
        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        had_recommendation_signal = has_profile_recommendation_signal(profile)
        profile.resume_text = "\n\n".join([item for item in [profile.resume_text, f"【{title}】\n{content}"] if item])
        force_recommendations = not had_recommendation_signal and has_profile_recommendation_signal(profile)
        resume_version = None
        if "简历" in title or str(data.get("section") or "") == "full":
            resume_version = await create_resume_version(
                session,
                profile,
                profile.resume_text,
                title=f"补充{title}",
                source="profile_note",
                optimized=0,
            )
            await ensure_candidate_profile(session, profile, force=True, source="profile_note")
        await session.commit()
        await session.refresh(profile)
        await remember_approved_action(profile, payload.tool, data, f"已补充到{title}。")
        await refresh_recommendations_after_commit(
            profile,
            trigger_reason="profile",
            source_type="profile",
            source_id=profile.id,
            force=force_recommendations,
        )
        return {
            "message": f"已补充到{title}。",
            "profile": serialize_profile(profile),
            "resume_version": serialize_resume_version(resume_version) if resume_version else None,
            "resume_versions": await serialized_resume_versions(session, profile.id),
        }

    if payload.tool == "add_knowledge_item":
        title = str(data.get("title") or "求职资料").strip()
        resource = KnowledgeResource(
            user_id=profile.id,
            title=title[:160],
            summary=str(data.get("summary") or data.get("content") or "")[:600],
            content=str(data.get("content") or ""),
            source="personal",
            url=str(data.get("url") or ""),
        )
        session.add(resource)
        await session.commit()
        await session.refresh(resource)
        await add_item_to_default_folder(session, profile.id, resource.id, "personal")
        await remember_approved_action(profile, payload.tool, data, "已添加到个人知识库。")
        await refresh_recommendations_after_commit(profile, trigger_reason="knowledge", source_type="knowledge", source_id=resource.id)
        return {"message": "已添加到个人知识库。", "knowledge": serialize_knowledge(resource)}

    if payload.tool == "update_knowledge_item":
        resource = await owned_knowledge(session, profile.id, str(data.get("id") or ""))
        for key in ["title", "summary", "content", "url"]:
            if key in data:
                setattr(resource, key, str(data.get(key) or ""))
        await session.commit()
        await session.refresh(resource)
        await refresh_recommendations_after_commit(profile, trigger_reason="knowledge", source_type="knowledge", source_id=resource.id)
        return {"message": "知识库资料已更新。", "knowledge": serialize_knowledge(resource)}

    if payload.tool == "delete_knowledge_item":
        resource = await owned_knowledge(session, profile.id, str(data.get("id") or ""))
        item_id = resource.id
        await session.delete(resource)
        await remove_item_from_folders(session, profile.id, item_id)
        await session.commit()
        await refresh_recommendations_after_commit(profile, trigger_reason="knowledge", source_type="knowledge", source_id=item_id)
        return {"message": "知识库资料已删除。", "deleted_knowledge_id": item_id}

    raise HTTPException(status_code=400, detail=f"unsupported tool: {payload.tool}")


@router.get("/knowledge")
async def list_knowledge(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    resources = (
        await session.execute(
            select(KnowledgeResource)
            .where(KnowledgeResource.user_id == profile.id)
            .order_by(desc(KnowledgeResource.created_at))
        )
    ).scalars().all()
    return {"items": [serialize_knowledge(item) for item in resources]}


@router.get("/knowledge/discover")
async def discover_knowledge() -> dict:
    return {"items": discover_knowledge_items()}


@router.get("/knowledge/folders")
async def list_knowledge_folders(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    folders = await ensure_default_folders(session, profile.id)
    return {"folders": [serialize_folder(folder) for folder in folders]}


@router.post("/knowledge/folders")
async def create_knowledge_folder(payload: KnowledgeFolderIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    folder = KnowledgeFolder(
        user_id=profile.id,
        name=payload.name.strip()[:120] or "新建文件夹",
        scope=normalize_folder_scope(payload.scope),
        item_ids=payload.item_ids,
        cover=payload.cover.strip()[:500],
        description=payload.description.strip()[:800],
        recommended_questions=normalize_recommended_questions(payload.recommended_questions),
        sort_order=payload.sort_order,
    )
    session.add(folder)
    await session.commit()
    await session.refresh(folder)
    return {"folder": serialize_folder(folder)}


@router.put("/knowledge/folders/{folder_id}")
async def update_knowledge_folder(folder_id: str, payload: KnowledgeFolderIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    folder = await owned_folder(session, profile.id, folder_id)
    folder.name = payload.name.strip()[:120] or folder.name
    folder.scope = normalize_folder_scope(payload.scope)
    folder.item_ids = payload.item_ids
    folder.cover = payload.cover.strip()[:500]
    folder.description = payload.description.strip()[:800]
    folder.recommended_questions = normalize_recommended_questions(payload.recommended_questions)
    folder.sort_order = payload.sort_order
    await session.commit()
    await session.refresh(folder)
    return {"folder": serialize_folder(folder)}


@router.delete("/knowledge/folders/{folder_id}")
async def delete_knowledge_folder(folder_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    folder = await owned_folder(session, profile.id, folder_id)
    await session.delete(folder)
    await session.commit()
    return {"deleted": True, "id": folder_id}


@router.post("/knowledge")
async def create_knowledge(payload: KnowledgeIn, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    resource = KnowledgeResource(
        user_id=profile.id,
        title=payload.title.strip()[:160] or "新建资料",
        summary=payload.summary,
        summary_status="ready",
        content=payload.content,
        source=payload.source,
        url=payload.url,
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    if payload.folder_id:
        await add_item_to_folder(session, profile.id, payload.folder_id, resource.id)
    else:
        await add_item_to_default_folder(session, profile.id, resource.id, "personal")
    await queue_knowledge_summary(session, background_tasks, resource)
    await refresh_recommendations_after_commit(profile, trigger_reason="knowledge", source_type="knowledge", source_id=resource.id)
    return {"item": serialize_knowledge(resource)}


@router.post("/knowledge/link")
async def create_knowledge_from_link(payload: KnowledgeLinkIn, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    try:
        parsed = await parse_link(payload.url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"link parse failed: {exc}") from exc
    resource = KnowledgeResource(
        user_id=profile.id,
        title=parsed.title[:160],
        summary=parsed.summary,
        summary_status="ready",
        content=parsed.content,
        source="personal",
        url=payload.url,
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    if payload.folder_id:
        await add_item_to_folder(session, profile.id, payload.folder_id, resource.id)
    else:
        await add_item_to_default_folder(session, profile.id, resource.id, "personal")
    await queue_knowledge_summary(session, background_tasks, resource)
    await refresh_recommendations_after_commit(profile, trigger_reason="knowledge", source_type="knowledge", source_id=resource.id)
    return {"item": serialize_knowledge(resource), "file": serialize_parsed_file(parsed, payload.url)}


@router.put("/knowledge/{item_id}")
async def update_knowledge(item_id: str, payload: KnowledgeIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    resource = await owned_knowledge(session, profile.id, item_id)
    resource.title = payload.title
    resource.summary = payload.summary
    resource.summary_status = "ready"
    resource.content = payload.content
    resource.source = payload.source
    resource.url = payload.url
    await session.commit()
    await session.refresh(resource)
    await refresh_recommendations_after_commit(profile, trigger_reason="knowledge", source_type="knowledge", source_id=resource.id)
    return {"item": serialize_knowledge(resource)}


@router.delete("/knowledge/{item_id}")
async def delete_knowledge(item_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    resource = await owned_knowledge(session, profile.id, item_id)
    await session.delete(resource)
    await remove_item_from_folders(session, profile.id, item_id)
    await session.commit()
    await refresh_recommendations_after_commit(profile, trigger_reason="knowledge", source_type="knowledge", source_id=item_id)
    return {"deleted": True, "id": item_id}


@router.post("/knowledge/{item_id}/summary")
async def refresh_knowledge_summary(
    item_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> dict:
    profile = await get_or_create_profile(session)
    resource = await owned_knowledge(session, profile.id, item_id)
    await queue_knowledge_summary(session, background_tasks, resource, force=True)
    return {"item": serialize_knowledge(resource)}


@router.post("/files/parse")
async def parse_file(file: UploadFile = File(...)) -> dict:
    parsed = await parse_uploaded_file(file)
    return {"file": parsed}


@router.post("/knowledge/upload")
async def upload_knowledge(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    folder_id: str = Form(""),
    session: AsyncSession = Depends(get_session),
) -> dict:
    profile = await get_or_create_profile(session)
    parsed = await parse_uploaded_file(file)
    resource = KnowledgeResource(
        user_id=profile.id,
        title=parsed["title"],
        summary=parsed["summary"],
        summary_status="ready",
        content=parsed["content"],
        source="personal",
        url="",
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    if folder_id:
        await add_item_to_folder(session, profile.id, folder_id, resource.id)
    else:
        await add_item_to_default_folder(session, profile.id, resource.id, "personal")
    await queue_knowledge_summary(session, background_tasks, resource)
    await refresh_recommendations_after_commit(profile, trigger_reason="knowledge", source_type="knowledge", source_id=resource.id)
    return {"item": serialize_knowledge(resource), "file": parsed}


def serialize_profile(profile: UserProfile) -> dict:
    return {
        "id": profile.id,
        "username": profile.username,
        "name": profile.name,
        "target_role": profile.target_role,
        "target_company": profile.target_company,
        "target_city": profile.target_city,
        "stage": profile.stage,
        "resume_text": profile.resume_text,
        "communication_style": profile.communication_style,
        "strengths": profile.strengths or [],
        "weak_points": profile.weak_points or [],
        "plan": profile.plan or [],
    }


def serialize_account(profile: UserProfile) -> dict:
    return {
        "username": profile.username,
        "display_name": profile.name,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }


def serialize_practice(record: PracticeRecord) -> dict:
    return {
        "id": record.id,
        "question": record.question,
        "answer": record.answer,
        "feedback": record.feedback,
        "score": record.score,
        "tags": record.tags or [],
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def serialize_interview(interview: InterviewSession) -> dict:
    return {
        "id": interview.id,
        "interview_type": interview.interview_type,
        "interviewer_style": interview.interviewer_style,
        "company": interview.company,
        "role": interview.role,
        "status": interview.status,
        "transcript": interview.transcript or [],
        "report": interview.report or {},
        "created_at": interview.created_at.isoformat() if interview.created_at else None,
    }


def serialize_memory(memory: AgentMemory) -> dict:
    return {
        "id": memory.id,
        "kind": memory.kind,
        "content": memory.content,
        "source": memory.source,
        "confidence": memory.confidence,
        "tags": memory.tags or [],
        "metadata": memory.memory_metadata or {},
        "use_count": memory.use_count or 0,
        "last_used_at": memory.last_used_at.isoformat() if memory.last_used_at else None,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
        "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
    }


def serialize_growth_update(update) -> dict:
    if not update:
        return {}
    return {
        "abilities": update.abilities,
        "issues": update.issues,
        "insights": update.insights,
        "actions": update.actions,
        "memory_updates": update.memory_updates,
    }


def serialize_knowledge(item: KnowledgeResource) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "summary": item.summary,
        "summary_status": item.summary_status or "ready",
        "content": item.content,
        "source": item.source,
        "url": item.url,
        "pinned": int(item.pinned or 0),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def serialize_folder(folder: KnowledgeFolder) -> dict:
    return {
        "id": folder.id,
        "name": folder.name,
        "scope": folder.scope,
        "item_ids": folder.item_ids or [],
        "cover": folder.cover or "",
        "description": folder.description or "",
        "recommended_questions": folder.recommended_questions or [],
        "sort_order": folder.sort_order,
        "created_at": folder.created_at.isoformat() if folder.created_at else None,
        "updated_at": folder.updated_at.isoformat() if folder.updated_at else None,
    }


def serialize_resume_version(resume: ResumeVersion | None) -> dict | None:
    if not resume:
        return None
    return {
        "id": resume.id,
        "title": resume.title,
        "filename": resume.filename,
        "summary": resume.summary,
        "content": resume.content,
        "size": len((resume.content or "").encode("utf-8")),
        "source": resume.source,
        "target_role": resume.target_role,
        "version_no": resume.version_no,
        "optimized": bool(resume.optimized),
        "created_at": resume.created_at.isoformat() if resume.created_at else None,
        "updated_at": resume.updated_at.isoformat() if resume.updated_at else None,
    }


def serialize_parsed_file(parsed, url: str = "") -> dict:
    return {
        "filename": parsed.filename,
        "extension": parsed.extension,
        "title": parsed.title,
        "summary": parsed.summary,
        "content": parsed.content,
        "size": len((parsed.content or "").encode("utf-8")),
        "warning": parsed.warning,
        "url": url,
    }


def normalize_folder_scope(scope: str) -> str:
    return "saved" if scope == "saved" else "personal"


async def list_recent_memories(session: AsyncSession, user_id: str, limit: int) -> list[AgentMemory]:
    return list((
        await session.execute(
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .order_by(desc(AgentMemory.updated_at))
            .limit(limit)
        )
    ).scalars().all())


async def serialized_resume_versions(session: AsyncSession, user_id: str, limit: int = 30) -> list[dict]:
    versions = (
        await session.execute(
            select(ResumeVersion)
            .where(ResumeVersion.user_id == user_id)
            .order_by(desc(ResumeVersion.created_at))
            .limit(limit)
        )
    ).scalars().all()
    return [item for item in (serialize_resume_version(version) for version in versions) if item]


async def create_resume_version(
    session: AsyncSession,
    profile: UserProfile,
    content: str,
    *,
    title: str = "完整简历",
    filename: str = "",
    source: str = "manual",
    optimized: int = 0,
) -> ResumeVersion | None:
    clean = normalize_resume_content(content)
    if not clean:
        return None
    latest = (
        await session.execute(
            select(ResumeVersion)
            .where(ResumeVersion.user_id == profile.id)
            .order_by(desc(ResumeVersion.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest and normalize_for_compare(latest.content) == normalize_for_compare(clean):
        return latest
    count = await session.scalar(select(func.count(ResumeVersion.id)).where(ResumeVersion.user_id == profile.id))
    resume = ResumeVersion(
        user_id=profile.id,
        title=(title or filename or "完整简历")[:180],
        filename=(filename or "")[:260],
        content=clean,
        summary=resume_summary(clean),
        source=source[:60],
        target_role=(profile.target_role or "")[:120],
        version_no=int(count or 0) + 1,
        optimized=1 if optimized else 0,
    )
    session.add(resume)
    await session.flush()
    return resume


async def owned_resume_version(session: AsyncSession, user_id: str, resume_id: str) -> ResumeVersion:
    resume = await session.get(ResumeVersion, resume_id)
    if not resume or resume.user_id != user_id:
        raise HTTPException(status_code=404, detail="resume version not found")
    return resume


def normalize_resume_content(content: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", str(content or "").replace("\r\n", "\n")).strip()


def normalize_for_compare(content: str) -> str:
    return re.sub(r"\s+", "", str(content or ""))


def resume_summary(content: str, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", content).strip()
    if not clean:
        return "暂无摘要"
    return clean[:limit] + ("..." if len(clean) > limit else "")


def profile_export_content(profile: UserProfile) -> str:
    lines = [
        f"# 桃子个人档案 - {profile.username}",
        "",
        f"- 姓名：{profile.name}",
        f"- 目标岗位：{profile.target_role}",
        f"- 目标公司：{profile.target_company or '未填写'}",
        f"- 求职阶段：{profile.stage}",
        f"- 沟通偏好：{profile.communication_style}",
        "",
        "## 完整简历",
        "",
        profile.resume_text or "暂无完整简历内容。",
        "",
        "## 优势",
        "",
        "\n".join(f"- {item}" for item in (profile.strengths or [])) or "暂无",
        "",
        "## 待提升",
        "",
        "\n".join(f"- {item}" for item in (profile.weak_points or [])) or "暂无",
    ]
    return "\n".join(lines).strip() + "\n"


def downloadable_text_response(content: str, filename: str, format: str) -> Response:
    ext = "txt" if format.lower() == "txt" else "md"
    media_type = "text/plain; charset=utf-8" if ext == "txt" else "text/markdown; charset=utf-8"
    safe_filename = re.sub(r"[^A-Za-z0-9_.-]+", "-", filename).strip("-") or "peach-export"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}.{ext}"'},
    )


async def relevant_memory_context(session: AsyncSession, profile: UserProfile, query: str, task_type: str = "chat") -> str:
    memories = await retrieve_relevant_memories(session, profile.id, query, task_type=task_type)
    return build_memory_context(memories)


async def remember_approved_action(
    profile: UserProfile,
    tool: str,
    payload: dict,
    message: str,
) -> None:
    summary = action_memory_summary(tool, payload, message)
    if not summary:
        return
    async with SessionLocal() as memory_session:
        try:
            await upsert_memory(
                memory_session,
                profile.id,
                {
                    "kind": "episodic_summary",
                    "content": summary,
                    "source": f"approved_action:{tool}",
                    "confidence": 75,
                    "tags": ["approved_action", tool],
                },
            )
            await memory_session.commit()
        except Exception:
            await memory_session.rollback()


async def refresh_recommendations_safely(
    session: AsyncSession,
    profile: UserProfile,
    *,
    trigger_reason: str,
    source_type: str = "",
    source_id: str = "",
    force: bool = False,
) -> None:
    try:
        await refresh_home_recommendations(
            session,
            profile,
            trigger_reason=trigger_reason,
            source_type=source_type,
            source_id=source_id,
            force=force,
        )
    except Exception:
        # 推荐刷新是体验增强，不能阻塞聊天、档案写入或面试报告生成。
        pass


async def refresh_recommendations_after_commit(
    profile: UserProfile,
    *,
    trigger_reason: str,
    source_type: str = "",
    source_id: str = "",
    force: bool = False,
) -> None:
    async with SessionLocal() as recommendation_session:
        try:
            current_profile = await recommendation_session.get(UserProfile, profile.id)
            if not current_profile:
                return
            await refresh_home_recommendations(
                recommendation_session,
                current_profile,
                trigger_reason=trigger_reason,
                source_type=source_type,
                source_id=source_id,
                force=force,
            )
            await recommendation_session.commit()
        except Exception:
            await recommendation_session.rollback()


async def cleanup_interview_related_data(session: AsyncSession, user_id: str, interview: InterviewSession) -> None:
    interview_id = interview.id
    title_bits = [interview.company or "", interview.role or ""]
    title_text = " ".join(item for item in title_bits if item).strip()
    memory_ids = (
        await session.execute(
            select(AgentMemory.id).where(
                AgentMemory.user_id == user_id,
                AgentMemory.source.in_(["interview_start", "interview_answer", "interview_report"]),
            )
        )
    ).scalars().all()
    removable_memory_ids: list[str] = []
    if memory_ids:
        memories = (await session.execute(select(AgentMemory).where(AgentMemory.id.in_(memory_ids)))).scalars().all()
        for memory in memories:
            metadata = memory.memory_metadata or {}
            content = memory.content or ""
            if (
                metadata.get("interview_id") == interview_id
                or interview_id in content
                or (title_text and title_text in content)
            ):
                removable_memory_ids.append(memory.id)

    await session.execute(delete(HomeRecommendation).where(HomeRecommendation.user_id == user_id, HomeRecommendation.source_id == interview_id))
    await session.execute(delete(AbilityScoreHistory).where(AbilityScoreHistory.user_id == user_id, AbilityScoreHistory.source_id == interview_id))
    issues = (await session.execute(select(GrowthIssue).where(GrowthIssue.user_id == user_id))).scalars().all()
    for issue in issues:
        if interview_id in (issue.evidence_ids or []):
            await session.delete(issue)
    insights = (await session.execute(select(GrowthInsight).where(GrowthInsight.user_id == user_id))).scalars().all()
    for insight in insights:
        if interview_id in (insight.evidence_ids or []):
            await session.delete(insight)
    actions = (await session.execute(select(ActionState).where(ActionState.user_id == user_id))).scalars().all()
    for action in actions:
        if interview_id in (action.related_experience_ids or []):
            await session.delete(action)

    if removable_memory_ids:
        await session.execute(delete(AgentMemory).where(AgentMemory.id.in_(removable_memory_ids)))
        await session.execute(
            delete(AgentMemoryEvent).where(
                AgentMemoryEvent.user_id == user_id,
                AgentMemoryEvent.memory_id.in_(removable_memory_ids),
            )
        )


def action_memory_summary(tool: str, payload: dict, message: str) -> str:
    if tool == "update_resume":
        mode = str(payload.get("mode") or "append")
        return f"用户确认{'替换' if mode == 'replace' else '追加'}完整简历，内容摘要：{str(payload.get('content') or '')[:180]}"
    if tool == "append_profile_note":
        title = str(payload.get("title") or "个人档案")
        return f"用户确认补充{title}，内容摘要：{str(payload.get('content') or '')[:180]}"
    if tool == "update_profile_fields":
        fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else payload
        return f"用户确认更新个人档案字段：{', '.join(str(key) for key in fields.keys())[:160]}"
    if tool == "add_knowledge_item":
        return f"用户确认新增知识库资料：{str(payload.get('title') or '求职资料')[:120]}"
    return message[:220]


async def ensure_default_folders(session: AsyncSession, user_id: str) -> list[KnowledgeFolder]:
    result = await session.execute(
        select(KnowledgeFolder).where(KnowledgeFolder.user_id == user_id).order_by(KnowledgeFolder.sort_order, KnowledgeFolder.created_at)
    )
    folders = list(result.scalars().all())
    existing_scopes = {folder.scope for folder in folders}
    changed = False
    if "personal" not in existing_scopes:
        folder = KnowledgeFolder(user_id=user_id, name="默认文件夹", scope="personal", item_ids=[], sort_order=0)
        session.add(folder)
        folders.append(folder)
        changed = True
    if "saved" not in existing_scopes:
        folder = KnowledgeFolder(user_id=user_id, name="默认收藏", scope="saved", item_ids=[], sort_order=0)
        session.add(folder)
        folders.append(folder)
        changed = True
    if changed:
        await session.commit()
        for folder in folders:
            await session.refresh(folder)

    resource_result = await session.execute(
        select(KnowledgeResource.id).where(KnowledgeResource.user_id == user_id, KnowledgeResource.source == "personal")
    )
    personal_resource_ids = [row[0] for row in resource_result.all()]
    if personal_resource_ids:
        personal_folders = [folder for folder in folders if folder.scope == "personal"]
        assigned_ids = {item_id for folder in personal_folders for item_id in (folder.item_ids or [])}
        orphan_ids = [item_id for item_id in personal_resource_ids if item_id not in assigned_ids]
        default_personal = next((folder for folder in personal_folders if folder.sort_order == 0), personal_folders[0] if personal_folders else None)
        if default_personal and orphan_ids:
            default_personal.item_ids = [*orphan_ids, *(default_personal.item_ids or [])]
            await session.commit()
            await session.refresh(default_personal)
    return folders


async def owned_folder(session: AsyncSession, user_id: str, folder_id: str) -> KnowledgeFolder:
    folder = await session.get(KnowledgeFolder, folder_id)
    if not folder or folder.user_id != user_id:
        raise HTTPException(status_code=404, detail="knowledge folder not found")
    return folder


async def add_item_to_folder(session: AsyncSession, user_id: str, folder_id: str, item_id: str) -> None:
    folder = await owned_folder(session, user_id, folder_id)
    item_ids = list(folder.item_ids or [])
    if item_id not in item_ids:
        folder.item_ids = [item_id, *item_ids]
        await session.commit()


async def add_item_to_default_folder(session: AsyncSession, user_id: str, item_id: str, scope: str) -> None:
    folders = await ensure_default_folders(session, user_id)
    folder = next((item for item in folders if item.scope == normalize_folder_scope(scope)), folders[0])
    await add_item_to_folder(session, user_id, folder.id, item_id)


async def remove_item_from_folders(session: AsyncSession, user_id: str, item_id: str) -> None:
    result = await session.execute(select(KnowledgeFolder).where(KnowledgeFolder.user_id == user_id))
    folders = result.scalars().all()
    for folder in folders:
        if item_id in (folder.item_ids or []):
            folder.item_ids = [value for value in folder.item_ids if value != item_id]


def discover_knowledge_items() -> list[dict]:
    items = [
        ("pm-method", "产品经理方法论题库", "覆盖用户洞察、需求判断、优先级、指标拆解和复盘表达。", "产品经理方法论题库，适合准备产品思维、项目深挖和 case 面试。"),
        ("aigc-strategy", "AIGC 策略产品面试资料", "整理大模型产品、内容生态、商业化和评估指标相关问题。", "AIGC 策略产品资料，包含模型能力、用户场景、指标设计和商业化问题。"),
        ("delivery-plan", "秋招投递节奏清单", "按时间、岗位和公司梯队拆解投递节奏。", "秋招投递节奏清单，覆盖提前批、正式批、补录和复盘安排。"),
        ("ai-pm-career", "AI 产品经理求职资料库", "覆盖 AI 产品方法论、岗位 JD 拆解、案例题和面试追问。", "AI 产品经理求职资料，包含 JD 拆解、简历表达、面试题和行动计划。"),
        ("resume-library", "产品简历表达库", "收集项目经历、实习经历、量化表达和 STAR 改写样例。", "产品简历表达库，帮助候选人把经历改写成有证据的简历 bullet。"),
        ("case-library", "商业分析与策略题库", "沉淀市场规模、增长策略、竞品分析和业务拆解题。", "商业分析和策略题库，适合练习结构化拆解和业务判断。"),
    ]
    return [
        {"id": item_id, "title": title, "summary": summary, "content": content, "source": "discover", "url": ""}
        for item_id, title, summary, content in items
    ]


def normalize_tool_action(action: dict, index: int) -> dict:
    allowed_tools = {
        "start_interview",
        "finish_latest_interview",
        "update_profile_fields",
        "update_resume",
        "append_profile_note",
        "add_knowledge_item",
        "update_knowledge_item",
        "delete_knowledge_item",
    }
    tool = str(action.get("tool", ""))
    if tool not in allowed_tools:
        return {
            "id": f"unsupported-{index}",
            "tool": "unsupported",
            "title": "无法执行的动作",
            "summary": "桃子提出了一个当前版本还不支持的动作。",
            "payload": {},
            "approval_required": True,
        }
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    payload = normalize_action_payload(tool, payload)
    return {
        "id": str(action.get("id") or f"{tool}-{index}"),
        "tool": tool,
        "title": str(action.get("title") or "待确认动作"),
        "summary": str(action.get("summary") or "确认后桃子会执行这个动作。"),
        "payload": payload,
        "approval_required": bool(action.get("approval_required", True)),
    }


def normalize_tool_actions_safely(actions: object) -> list[dict]:
    if not isinstance(actions, list):
        return []
    normalized: list[dict] = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        try:
            normalized.append(normalize_tool_action(action, index))
        except Exception:
            continue
    return normalized


def normalize_action_payload(tool: str, payload: dict) -> dict:
    normalized = dict(payload)
    if tool not in {
        "update_profile_fields",
        "update_resume",
        "append_profile_note",
        "add_knowledge_item",
        "update_knowledge_item",
        "delete_knowledge_item",
    }:
        return normalized

    normalized["write_policy"] = "confirm_only_no_llm"
    normalized.setdefault("draft_ready", True)

    if tool == "update_profile_fields":
        fields = normalized.get("fields")
        if not isinstance(fields, dict):
            fields = {key: value for key, value in normalized.items() if key in {"name", "target_role", "target_company", "target_city", "stage", "communication_style"}}
            normalized["fields"] = fields
        normalized.setdefault("diff_summary", [f"更新字段：{key}" for key in fields.keys()])
        normalized.setdefault("preview", "；".join(f"{key}={str(value)[:80]}" for key, value in fields.items()))

    if tool == "update_resume":
        content = str(normalized.get("content") or "").strip()
        mode = str(normalized.get("mode") or "append")
        normalized["mode"] = "replace" if mode == "replace" else "append"
        normalized["content"] = content
        normalized.setdefault(
            "diff_summary",
            [
                "替换完整简历正文" if normalized["mode"] == "replace" else "追加到完整简历末尾",
                f"草案字数：{len(content)}",
            ],
        )
        normalized.setdefault("preview", content[:1200])

    if tool == "append_profile_note":
        content = str(normalized.get("content") or "").strip()
        normalized["content"] = content
        normalized.setdefault("section", "full")
        normalized.setdefault("title", "个人档案")
        normalized.setdefault(
            "diff_summary",
            [
                f"写入分区：{normalized.get('title')}",
                f"新增字数：{len(content)}",
            ],
        )
        normalized.setdefault("preview", content[:1200])

    if tool == "add_knowledge_item":
        content = str(normalized.get("content") or "").strip()
        normalized.setdefault("title", "求职资料")
        normalized.setdefault("summary", content[:180])
        normalized.setdefault(
            "diff_summary",
            [
                f"新增资料：{normalized.get('title')}",
                f"正文长度：{len(content)}",
            ],
        )
        normalized.setdefault("preview", content[:1200] or str(normalized.get("summary") or ""))

    if tool == "update_knowledge_item":
        changed = [key for key in ["title", "summary", "content", "url"] if key in normalized]
        normalized.setdefault("diff_summary", [f"更新知识库字段：{key}" for key in changed])
        normalized.setdefault("preview", str(normalized.get("content") or normalized.get("summary") or "")[:1200])

    if tool == "delete_knowledge_item":
        normalized.setdefault("diff_summary", [f"删除资料 ID：{normalized.get('id') or '未提供'}"])
        normalized.setdefault("preview", "确认后会从个人知识库移除这条资料。")

    return normalized


async def latest_interview(session: AsyncSession, user_id: str, active_only: bool) -> InterviewSession | None:
    query = select(InterviewSession).where(InterviewSession.user_id == user_id)
    if active_only:
        query = query.where(InterviewSession.status == "active")
    result = await session.execute(query.order_by(desc(InterviewSession.created_at)).limit(1))
    return result.scalar_one_or_none()


def build_interview_progress(interview: InterviewSession) -> dict:
    transcript = interview.transcript or []
    answer_count = sum(1 for item in transcript if item.get("role") == "candidate")
    question_count = sum(1 for item in transcript if item.get("role") == "interviewer")
    candidate_text = "\n".join(str(item.get("content") or "") for item in transcript if item.get("role") == "candidate")
    checklist = build_interview_checklist(candidate_text, answer_count)
    covered_count = sum(1 for item in checklist if item["done"])
    completion = 0 if answer_count == 0 else min(100, round(covered_count / len(INTERVIEW_CHECKLIST) * 100))
    return {
        "answer_count": answer_count,
        "question_count": question_count,
        "min_answers_for_llm_finish": MIN_INTERVIEW_ANSWERS_FOR_LLM_FINISH,
        "target_answers": TARGET_INTERVIEW_ANSWERS,
        "max_answers": MAX_INTERVIEW_ANSWERS,
        "completion": completion,
        "checklist": checklist,
        "can_llm_finish": answer_count >= MIN_INTERVIEW_ANSWERS_FOR_LLM_FINISH and covered_count >= 5,
    }


def build_interview_checklist(transcript_text: str, answer_count: int) -> list[dict]:
    text = transcript_text.lower()
    keyword_groups = {
        "self_intro": ["自我介绍", "我是", "来自", "背景", "经历"],
        "experience_deep_dive": ["实习", "项目", "负责", "主导", "推动", "star", "结果"],
        "role_understanding": ["岗位", "公司", "用户", "业务", "产品", "策略", "jd", "行业"],
        "evidence_quality": ["数据", "%", "提升", "增长", "降低", "指标", "上线", "转化", "留存"],
        "pressure_followup": ["质疑", "挑战", "如果", "为什么", "不是你", "压力", "反驳"],
        "closing_readiness": ["复盘", "总结", "下一步", "改进", "收尾"],
    }
    checklist = []
    for key, label, description in INTERVIEW_CHECKLIST:
        matched = answer_count > 0 and any(word in text for word in keyword_groups.get(key, []))
        if key == "self_intro":
            matched = matched or answer_count >= 1
        if key == "experience_deep_dive":
            matched = matched or answer_count >= 3
        if key == "role_understanding":
            matched = matched or answer_count >= 4
        if key == "pressure_followup":
            matched = matched or answer_count >= 6
        if key == "closing_readiness":
            matched = matched or answer_count >= 8
        checklist.append({"key": key, "label": label, "description": description, "done": matched})
    return checklist


async def owned_knowledge(session: AsyncSession, user_id: str, item_id: str) -> KnowledgeResource:
    resource = await session.get(KnowledgeResource, item_id)
    if not resource or resource.user_id != user_id:
        raise HTTPException(status_code=404, detail="knowledge item not found")
    return resource


async def owned_interview(session: AsyncSession, user_id: str, interview_id: str) -> InterviewSession:
    interview = await session.get(InterviewSession, interview_id)
    if not interview or interview.user_id != user_id:
        raise HTTPException(status_code=404, detail="interview not found")
    return interview


def candidate_profile_completeness(field_statuses: dict) -> int:
    values = field_statuses.values() if isinstance(field_statuses, dict) else []
    scores = [1 if value == "confirmed" else 0.45 if value == "uncertain" else 0 for value in values]
    if not scores:
        return 0
    return round(sum(scores) / len(scores) * 100)


def normalize_recommended_questions(values: list[str] | None) -> list[str]:
    questions: list[str] = []
    for value in values or []:
        text_value = re.sub(r"\s+", " ", str(value or "")).strip()
        if text_value and text_value not in questions:
            questions.append(text_value[:80])
        if len(questions) >= 8:
            break
    return questions


def fallback_knowledge_summary(title: str, content: str) -> str:
    clean = re.sub(r"\s+", " ", content or "").strip()
    if not clean:
        return f"{title or '这份资料'}暂无可总结内容。"
    return f"这份资料主要包含：{clean[:180]}{'...' if len(clean) > 180 else ''}"


def clean_knowledge_summary(value: str, title: str, content: str) -> str:
    clean = re.sub(r"\s+", " ", value or "").strip()
    clean = re.sub(r"^(摘要|总结|资料摘要)[:：]\s*", "", clean)
    if not clean:
        return fallback_knowledge_summary(title, content)
    return clean[:420]


async def queue_knowledge_summary(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    resource: KnowledgeResource,
    *,
    force: bool = False,
) -> None:
    content = (resource.content or "").strip()
    if not content or (not force and len(content) < 120):
        resource.summary_status = "ready"
        await session.commit()
        await session.refresh(resource)
        return
    resource.summary_status = "queued"
    await session.commit()
    await session.refresh(resource)
    background_tasks.add_task(generate_knowledge_summary, resource.id)


async def generate_knowledge_summary(item_id: str) -> None:
    async with SessionLocal() as session:
        resource = await session.get(KnowledgeResource, item_id)
        if not resource:
            return
        resource.summary_status = "running"
        await session.commit()
        content = (resource.content or "").strip()
        fallback = fallback_knowledge_summary(resource.title, content)
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是求职知识库整理助手。请把用户上传的资料总结成真正的资料摘要，"
                    "不要照抄开头，不要输出 Markdown，不要编造。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"资料标题：{resource.title}\n\n"
                    f"资料正文：{content[:6000]}\n\n"
                    "请用 1 到 2 句中文总结这份资料的主题、关键信息和可用于求职准备的价值，控制在 120 字以内。"
                ),
            },
        ]
        try:
            summary = await agent.complete(prompt, fallback=fallback, allow_fallback=True)
            resource.summary = clean_knowledge_summary(summary, resource.title, content)
            resource.summary_status = "ready"
        except Exception:
            resource.summary = fallback
            resource.summary_status = "failed"
        await session.commit()


async def parse_uploaded_file(file: UploadFile) -> dict:
    filename = file.filename or "upload"
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"unsupported file type. allowed: {allowed}")

    content = await file.read()
    if len(content) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file is too large")

    try:
        parsed = parse_upload(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"file parse failed: {exc}") from exc

    return {
        "filename": parsed.filename,
        "extension": parsed.extension,
        "title": parsed.filename or filename,
        "summary": parsed.summary,
        "content": parsed.content,
        "size": len(content),
        "warning": parsed.warning,
    }


def build_growth(
    profile: UserProfile,
    records: list[PracticeRecord],
    interviews: list[InterviewSession],
) -> dict:
    scored = [item.score for item in records if item.score]
    avg_score = round(sum(scored) / len(scored)) if scored else 0
    completed_interviews = [item for item in interviews if item.status == "completed"]
    return {
        "avg_score": avg_score,
        "practice_count": len(records),
        "interview_count": len(interviews),
        "completed_interview_count": len(completed_interviews),
        "strengths": profile.strengths or [],
        "weak_points": profile.weak_points or [],
        "progress_points": [
            {"label": item.created_at.strftime("%m-%d") if item.created_at else "今日", "score": item.score}
            for item in reversed(records)
            if item.score
        ],
    }


def build_local_checkin(profile: UserProfile, records: list[PracticeRecord]) -> dict:
    weak_point = (profile.weak_points or ["回答结构"])[0]
    if records:
        question = f"我们复练上一类题：请用 90 秒回答“为什么你适合{profile.target_role}”，重点修正「{weak_point}」。"
        title = "复练薄弱点"
        focus = f"先给结论，再用经历证明，最后落到{profile.target_role}的岗位匹配。"
    else:
        question = f"请用 1 分钟介绍你自己，并说明为什么你适合{profile.target_role}。"
        title = "每日一练：自我介绍开场"
        focus = "开头 30 秒要稳：身份、亮点、岗位匹配三件事讲清楚。"
    return {
        "message": f"{profile.name}，今天状态怎么样？我们先用 8 分钟练一题，稳稳往前推一步。",
        "task": {
            "title": title,
            "question": question,
            "duration": "5-10 分钟",
            "focus": focus,
        },
    }


def default_plan() -> list[dict]:
    return [
        {"day": 1, "title": "30 秒自我介绍", "focus": "把经历、目标和岗位连接起来"},
        {"day": 2, "title": "STAR 行为题", "focus": "用结果和数据支撑故事"},
        {"day": 3, "title": "产品思维题", "focus": "先框架后细节，避免想到哪说到哪"},
    ]


def merge_points(existing: list[str] | None, incoming: list[str] | None, limit: int = 6) -> list[str]:
    values: list[str] = []
    for item in [*(incoming or []), *(existing or [])]:
        if item and item not in values:
            values.append(item)
    return values[:limit]
