from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_session
from backend.app.models import InterviewSession, KnowledgeResource, PracticeRecord, UserProfile
from backend.app.schemas import (
    AgentActionIn,
    AgentToolExecuteIn,
    ChatIn,
    InterviewAnswerIn,
    InterviewStartIn,
    KnowledgeIn,
    PracticeIn,
    ProfileIn,
    ReviewIn,
)
from backend.app.services.agent import PeachAgent
from backend.app.services.file_parser import SUPPORTED_EXTENSIONS, parse_upload

router = APIRouter(prefix="/api")
agent = PeachAgent()


async def get_or_create_profile(session: AsyncSession) -> UserProfile:
    result = await session.execute(select(UserProfile).order_by(UserProfile.created_at).limit(1))
    profile = result.scalar_one_or_none()
    if profile:
        return profile

    profile = UserProfile(
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
    await session.commit()
    await session.refresh(profile)
    return profile


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "peach-agent"}


@router.get("/profile")
async def read_profile(session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    return serialize_profile(profile)


@router.post("/profile")
async def upsert_profile(payload: ProfileIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)

    init = await agent.initialize_profile(profile)
    profile.strengths = init.get("strengths", [])
    profile.weak_points = init.get("weak_points", [])
    profile.plan = init.get("plan", [])
    await session.commit()
    await session.refresh(profile)
    return {"profile": serialize_profile(profile), "greeting": init.get("greeting", "")}


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

    return {
        "profile": serialize_profile(profile),
        "checkin": checkin,
        "recent_practices": [serialize_practice(item) for item in records],
        "recent_interviews": [serialize_interview(item) for item in interviews],
        "growth": build_growth(profile, list(records), list(interviews)),
    }


@router.post("/practice")
async def submit_practice(payload: PracticeIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    feedback = await agent.evaluate_practice(profile, payload.question, payload.answer)
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
    await session.commit()
    await session.refresh(record)
    return {"record": serialize_practice(record), "feedback": feedback}


@router.post("/interviews")
async def start_interview(payload: InterviewStartIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
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
        {"jd": payload.jd, "question_bank": payload.question_bank},
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
        {"role": "interviewer", "content": opening["opening"]},
        {"role": "interviewer", "content": opening["question"]},
    ]
    session.add(interview)
    await session.commit()
    await session.refresh(interview)
    return {"interview": serialize_interview(interview), "opening": opening}


@router.post("/interviews/{interview_id}/answer")
async def answer_interview(
    interview_id: str,
    payload: InterviewAnswerIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    profile = await get_or_create_profile(session)
    interview = await session.get(InterviewSession, interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="interview not found")

    transcript = [*interview.transcript, {"role": "candidate", "content": payload.answer}]
    interview.transcript = transcript
    next_turn = await agent.continue_interview(profile, interview, payload.answer)
    interview.transcript = [
        *interview.transcript,
        {"role": "interviewer", "content": next_turn["micro_feedback"]},
        {"role": "interviewer", "content": next_turn["next_question"]},
    ]

    if next_turn.get("should_finish"):
        interview.status = "completed"
        interview.report = await agent.interview_report(profile, interview)

    await session.commit()
    await session.refresh(interview)
    return {"interview": serialize_interview(interview), "next": next_turn, "report": interview.report}


@router.post("/interviews/{interview_id}/finish")
async def finish_interview(interview_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    interview = await session.get(InterviewSession, interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="interview not found")

    interview.status = "completed"
    interview.report = await agent.interview_report(profile, interview)
    await session.commit()
    await session.refresh(interview)
    return {"interview": serialize_interview(interview), "report": interview.report}


@router.post("/review")
async def review(payload: ReviewIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    feedback = await agent.post_interview_review(profile, payload.model_dump())
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
    await session.commit()
    await session.refresh(record)
    return {"review": feedback, "record": serialize_practice(record)}


@router.post("/chat")
async def chat(payload: ChatIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    reply = await agent.chat(profile, payload.message)
    return {"reply": reply}


@router.post("/agent/actions")
async def agent_actions(payload: AgentActionIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    planned = await agent.plan_actions(profile, payload.message, payload.context)
    return {
        "reply": planned.get("reply", ""),
        "actions": [normalize_tool_action(action, index) for index, action in enumerate(planned.get("actions", []))],
    }


@router.post("/agent/actions/execute")
async def execute_agent_action(payload: AgentToolExecuteIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    data = payload.payload or {}

    if payload.tool == "start_interview":
        interview_payload = InterviewStartIn(
            interview_type=str(data.get("interview_type") or "模拟面试"),
            interviewer_style=str(data.get("interviewer_style") or "温和型"),
            company=str(data.get("company") or profile.target_company or ""),
            role=str(data.get("role") or profile.target_role),
            jd=str(data.get("jd") or ""),
            question_bank=str(data.get("question_bank") or ""),
        )
        result = await start_interview(interview_payload, session)
        return {"message": "已创建模拟面试。", **result}

    if payload.tool == "finish_latest_interview":
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
        allowed = {"name", "target_role", "target_company", "target_city", "stage", "communication_style"}
        for key, value in fields.items():
            if key in allowed:
                setattr(profile, key, str(value))
        init = await agent.initialize_profile(profile)
        profile.strengths = init.get("strengths", profile.strengths or [])
        profile.weak_points = init.get("weak_points", profile.weak_points or [])
        profile.plan = init.get("plan", profile.plan or [])
        await session.commit()
        await session.refresh(profile)
        return {"message": "个人信息已更新。", "profile": serialize_profile(profile)}

    if payload.tool == "update_resume":
        content = str(data.get("content") or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        mode = str(data.get("mode") or "append")
        profile.resume_text = content if mode == "replace" else "\n\n".join([item for item in [profile.resume_text, content] if item])
        init = await agent.initialize_profile(profile)
        profile.strengths = init.get("strengths", profile.strengths or [])
        profile.weak_points = init.get("weak_points", profile.weak_points or [])
        profile.plan = init.get("plan", profile.plan or [])
        await session.commit()
        await session.refresh(profile)
        return {"message": "简历已更新。", "profile": serialize_profile(profile)}

    if payload.tool == "append_profile_note":
        content = str(data.get("content") or "").strip()
        title = str(data.get("title") or "个人档案")
        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        profile.resume_text = "\n\n".join([item for item in [profile.resume_text, f"【{title}】\n{content}"] if item])
        await session.commit()
        await session.refresh(profile)
        return {"message": f"已补充到{title}。", "profile": serialize_profile(profile)}

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
        return {"message": "已添加到个人知识库。", "knowledge": serialize_knowledge(resource)}

    if payload.tool == "update_knowledge_item":
        resource = await owned_knowledge(session, profile.id, str(data.get("id") or ""))
        for key in ["title", "summary", "content", "url"]:
            if key in data:
                setattr(resource, key, str(data.get(key) or ""))
        await session.commit()
        await session.refresh(resource)
        return {"message": "知识库资料已更新。", "knowledge": serialize_knowledge(resource)}

    if payload.tool == "delete_knowledge_item":
        resource = await owned_knowledge(session, profile.id, str(data.get("id") or ""))
        item_id = resource.id
        await session.delete(resource)
        await session.commit()
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


@router.post("/knowledge")
async def create_knowledge(payload: KnowledgeIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    resource = KnowledgeResource(
        user_id=profile.id,
        title=payload.title,
        summary=payload.summary,
        content=payload.content,
        source=payload.source,
        url=payload.url,
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return {"item": serialize_knowledge(resource)}


@router.put("/knowledge/{item_id}")
async def update_knowledge(item_id: str, payload: KnowledgeIn, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    resource = await owned_knowledge(session, profile.id, item_id)
    resource.title = payload.title
    resource.summary = payload.summary
    resource.content = payload.content
    resource.source = payload.source
    resource.url = payload.url
    await session.commit()
    await session.refresh(resource)
    return {"item": serialize_knowledge(resource)}


@router.delete("/knowledge/{item_id}")
async def delete_knowledge(item_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    resource = await owned_knowledge(session, profile.id, item_id)
    await session.delete(resource)
    await session.commit()
    return {"deleted": True, "id": item_id}


@router.post("/files/parse")
async def parse_file(file: UploadFile = File(...)) -> dict:
    parsed = await parse_uploaded_file(file)
    return {"file": parsed}


@router.post("/knowledge/upload")
async def upload_knowledge(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)) -> dict:
    profile = await get_or_create_profile(session)
    parsed = await parse_uploaded_file(file)
    resource = KnowledgeResource(
        user_id=profile.id,
        title=parsed["title"],
        summary=parsed["summary"],
        content=parsed["content"],
        source="personal",
        url="",
    )
    session.add(resource)
    await session.commit()
    await session.refresh(resource)
    return {"item": serialize_knowledge(resource), "file": parsed}


def serialize_profile(profile: UserProfile) -> dict:
    return {
        "id": profile.id,
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


def serialize_knowledge(item: KnowledgeResource) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "summary": item.summary,
        "content": item.content,
        "source": item.source,
        "url": item.url,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


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
    return {
        "id": str(action.get("id") or f"{tool}-{index}"),
        "tool": tool,
        "title": str(action.get("title") or "待确认动作"),
        "summary": str(action.get("summary") or "确认后桃子会执行这个动作。"),
        "payload": action.get("payload") if isinstance(action.get("payload"), dict) else {},
        "approval_required": bool(action.get("approval_required", True)),
    }


async def latest_interview(session: AsyncSession, user_id: str, active_only: bool) -> InterviewSession | None:
    query = select(InterviewSession).where(InterviewSession.user_id == user_id)
    if active_only:
        query = query.where(InterviewSession.status == "active")
    result = await session.execute(query.order_by(desc(InterviewSession.created_at)).limit(1))
    return result.scalar_one_or_none()


async def owned_knowledge(session: AsyncSession, user_id: str, item_id: str) -> KnowledgeResource:
    resource = await session.get(KnowledgeResource, item_id)
    if not resource or resource.user_id != user_id:
        raise HTTPException(status_code=404, detail="knowledge item not found")
    return resource


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
        "title": parsed.title,
        "summary": parsed.summary,
        "content": parsed.content,
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
