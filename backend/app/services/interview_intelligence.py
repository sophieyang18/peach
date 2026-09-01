from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import InterviewExperience, InterviewQuestion, InterviewQuestionSet, UserProfile


QUESTION_MIX = {
    "real_experience": 0.2,
    "resume_specific": 0.4,
    "jd_specific": 0.2,
    "growth_specific": 0.2,
}


async def import_experience(session: AsyncSession, profile: UserProfile, payload) -> tuple[InterviewExperience, list[InterviewQuestion]]:
    experience = InterviewExperience(
        user_id=profile.id,
        company=short_text(payload.company, 120),
        role=short_text(payload.role or profile.target_role, 120),
        department=short_text(payload.department, 120),
        interview_stage=short_text(payload.interview_stage or profile.stage, 80),
        interview_date=short_text(payload.interview_date, 40),
        raw_content=str(payload.raw_content or "")[:20000],
        source_type=short_text(payload.source_type or "manual", 60),
        source_name=short_text(payload.source_name or "手动导入", 160),
        source_url=str(payload.source_url or "")[:1000],
        published_at=short_text(payload.published_at, 40),
        status="imported",
    )
    session.add(experience)
    await session.flush()

    questions: list[InterviewQuestion] = []
    for extracted in extract_questions(experience.raw_content):
        question = await upsert_question(session, experience, extracted)
        questions.append(question)
    experience.status = "processed" if questions else "no_questions"
    await session.flush()
    return experience, questions


async def list_questions(
    session: AsyncSession,
    profile: UserProfile,
    *,
    company: str = "",
    role: str = "",
    interview_stage: str = "",
) -> list[InterviewQuestion]:
    query = select(InterviewQuestion)
    filters = []
    if company:
        filters.append(InterviewQuestion.company == company)
    if role:
        filters.append(InterviewQuestion.role == role)
    if interview_stage:
        filters.append(InterviewQuestion.interview_stage == interview_stage)
    if filters:
        query = query.where(*filters)
    query = query.order_by(desc(InterviewQuestion.source_count), desc(InterviewQuestion.last_seen_at)).limit(80)
    return (await session.execute(query)).scalars().all()


async def build_question_set(session: AsyncSession, profile: UserProfile, payload) -> InterviewQuestionSet:
    company = short_text(payload.company or profile.target_company, 120)
    role = short_text(payload.role or profile.target_role, 120)
    stage = short_text(payload.interview_stage or profile.stage, 80)
    limit = max(4, min(12, int(payload.limit or 10)))
    questions = await list_questions(session, profile, company=company, role=role, interview_stage=stage)
    if len(questions) < limit:
        broader = await list_questions(session, profile, company=company, role=role)
        questions = merge_questions([*questions, *broader])
    if len(questions) < limit:
        broader = await list_questions(session, profile, role=role)
        questions = merge_questions([*questions, *broader])

    selected = [personalize_question(item, profile, payload.jd) for item in questions[:limit]]
    while len(selected) < min(limit, 6):
        selected.append(fallback_question(len(selected), profile, company, role, stage, payload.jd))

    question_set = InterviewQuestionSet(
        user_id=profile.id,
        company=company,
        role=role,
        interview_stage=stage,
        questions=selected,
        mix=QUESTION_MIX,
        source_summary={
            "real_question_count": len([item for item in selected if item.get("source_type") == "real_experience"]),
            "fallback_count": len([item for item in selected if item.get("source_type") != "real_experience"]),
            "sample_notice": "基于当前收录公开面经样本；样本不足时回退到 JD、简历和能力模型题。",
        },
    )
    session.add(question_set)
    await session.flush()
    return question_set


async def upsert_question(session: AsyncSession, experience: InterviewExperience, extracted: dict[str, Any]) -> InterviewQuestion:
    normalized = normalize_question(extracted["question"])
    existing = (
        await session.execute(
            select(InterviewQuestion)
            .where(
                InterviewQuestion.normalized_question == normalized,
                InterviewQuestion.company == experience.company,
                InterviewQuestion.role == experience.role,
                InterviewQuestion.interview_stage == experience.interview_stage,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        source_ids = list(dict.fromkeys([*(existing.source_ids or []), experience.id]))
        existing.source_ids = source_ids
        existing.source_count = len(source_ids)
        existing.last_seen_at = datetime.now(timezone.utc)
        existing.popularity_score = min(100, 45 + existing.source_count * 10)
        return existing

    question = InterviewQuestion(
        canonical_question=extracted["question"][:1000],
        normalized_question=normalized,
        company=experience.company,
        role=experience.role,
        interview_stage=experience.interview_stage,
        assessment_point=classify_assessment_point(extracted["question"]),
        secondary_points=[],
        question_type=extracted["question_type"],
        explicit=1 if extracted["explicit"] else 0,
        difficulty=classify_difficulty(extracted["question"]),
        source_count=1,
        source_ids=[experience.id],
        popularity_score=55,
        recency_score=60,
    )
    session.add(question)
    return question


def extract_questions(raw: str) -> list[dict[str, Any]]:
    text = re.sub(r"\r\n?", "\n", str(raw or ""))
    candidates: list[str] = []
    for line in text.splitlines():
        clean = line.strip(" \t-•0123456789.、")
        if not clean:
            continue
        if "?" in clean or "？" in clean or re.search(r"(问|问题|追问|面试官).*[:：]", clean):
            candidates.append(re.sub(r"^(问|问题|追问|面试官)[:：]\s*", "", clean))
    if not candidates:
        candidates = re.findall(r"[^。！？\n]{4,80}[？?]", text)
    topic_signals = []
    if not candidates and re.search(r"(深挖|重点聊|主要问|围绕).{0,20}(项目|实习|简历|数据|业务)", text):
        topic_signals.append("围绕项目或实习经历做深挖")
    return [
        {
            "question": short_text(item, 300),
            "question_type": classify_question_type(item),
            "explicit": item not in topic_signals,
        }
        for item in merge_texts([*candidates, *topic_signals])[:20]
    ]


def personalize_question(question: InterviewQuestion, profile: UserProfile, jd: str = "") -> dict[str, Any]:
    resume_hint = first_project_hint(profile.resume_text)
    text = question.canonical_question
    if resume_hint and question.assessment_point in {"project_deep_dive", "project_decision_reasoning", "data_attribution"}:
        text = f"结合你简历里的「{resume_hint}」，{text}"
    elif jd and question.assessment_point in {"role_understanding", "company_understanding"}:
        text = f"结合这份 JD，{text}"
    return {
        "question": text,
        "source_question_id": question.id,
        "source_type": "real_experience" if question.explicit else "topic_signal",
        "assessment_point": question.assessment_point,
        "resume_evidence": resume_hint,
        "generation_reason": "真实面经题结合用户简历改写" if resume_hint else "来自已导入面经题库",
    }


def fallback_question(index: int, profile: UserProfile, company: str, role: str, stage: str, jd: str) -> dict[str, Any]:
    templates = [
        "请先做一个 1 分钟自我介绍。",
        f"为什么想投 {company or '这家公司'} 的 {role or profile.target_role}？",
        "挑一段最能证明你产品能力的项目，讲清楚背景、动作和结果。",
        "你在项目里做过最关键的一个取舍是什么？依据是什么？",
        "如果数据结果不符合预期，你会怎么定位问题？",
        "你还有什么想反问我的？",
    ]
    question = templates[index % len(templates)]
    if jd and index == 1:
        question = f"结合 JD，{question}"
    return {
        "question": question,
        "source_question_id": "",
        "source_type": "fallback_competency",
        "assessment_point": classify_assessment_point(question),
        "resume_evidence": first_project_hint(profile.resume_text),
        "generation_reason": f"{stage or '当前轮次'}样本不足，回退到 JD、简历和通用能力模型。",
    }


def serialize_experience(item: InterviewExperience) -> dict[str, Any]:
    return {
        "id": item.id,
        "company": item.company,
        "role": item.role,
        "department": item.department,
        "interview_stage": item.interview_stage,
        "source_type": item.source_type,
        "source_name": item.source_name,
        "source_url": item.source_url,
        "published_at": item.published_at,
        "status": item.status,
        "imported_at": item.imported_at.isoformat() if item.imported_at else None,
    }


def serialize_question(item: InterviewQuestion) -> dict[str, Any]:
    return {
        "id": item.id,
        "canonical_question": item.canonical_question,
        "company": item.company,
        "role": item.role,
        "interview_stage": item.interview_stage,
        "assessment_point": item.assessment_point,
        "question_type": item.question_type,
        "explicit": bool(item.explicit),
        "difficulty": item.difficulty,
        "source_count": item.source_count,
        "source_ids": item.source_ids or [],
    }


def serialize_question_set(item: InterviewQuestionSet) -> dict[str, Any]:
    return {
        "id": item.id,
        "company": item.company,
        "role": item.role,
        "interview_stage": item.interview_stage,
        "questions": item.questions or [],
        "mix": item.mix or QUESTION_MIX,
        "source_summary": item.source_summary or {},
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def merge_questions(items: list[InterviewQuestion]) -> list[InterviewQuestion]:
    seen: set[str] = set()
    merged: list[InterviewQuestion] = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        merged.append(item)
    return merged


def merge_texts(items: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for item in items:
        normalized = normalize_question(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(item)
    return merged


def normalize_question(value: str) -> str:
    return re.sub(r"[\s，。！？?、,.；;：:]+", "", str(value or "").lower())[:240]


def classify_question_type(value: str) -> str:
    if re.search(r"(项目|实习|经历|负责|做过)", value):
        return "experience"
    if re.search(r"(设计|方案|功能|产品)", value):
        return "product_design"
    if re.search(r"(数据|指标|实验|ab|归因)", value, re.I):
        return "data"
    if re.search(r"(为什么|动机|职业|岗位|公司)", value):
        return "motivation"
    return "general"


def classify_assessment_point(value: str) -> str:
    if re.search(r"(数据|指标|实验|归因|提升|转化)", value, re.I):
        return "data_attribution"
    if re.search(r"(为什么|决策|取舍|优先|依据)", value):
        return "project_decision_reasoning"
    if re.search(r"(公司|岗位|投|业务)", value):
        return "role_understanding"
    if re.search(r"(自我介绍|介绍一下)", value):
        return "self_introduction"
    if re.search(r"(项目|实习|经历)", value):
        return "project_deep_dive"
    return "structured_expression"


def classify_difficulty(value: str) -> str:
    return "hard" if re.search(r"(质疑|反驳|失败|缺点|为什么不|如果.*不)", value) else "medium"


def first_project_hint(resume_text: str) -> str:
    match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{2,24}(?:项目|Agent|平台|系统|工具))", resume_text or "")
    return match.group(1) if match else ""


def short_text(value: str, limit: int) -> str:
    clean = " ".join(str(value or "").split())
    return clean[:limit]
