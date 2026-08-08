from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_session
from backend.app.models import InterviewSession, PracticeRecord, UserProfile
from backend.app.schemas import (
    ChatIn,
    InterviewAnswerIn,
    InterviewStartIn,
    PracticeIn,
    ProfileIn,
    ReviewIn,
)
from backend.app.services.agent import PeachAgent

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
    opening = await agent.start_interview(profile, interview)
    interview.transcript = [
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
