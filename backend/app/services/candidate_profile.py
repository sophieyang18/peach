from __future__ import annotations

import re
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import CandidateProfile, ResumeVersion, UserProfile


PROFILE_FIELDS = [
    "basics.name",
    "target_preferences.role",
    "target_preferences.company",
    "education",
    "experiences",
    "projects",
    "skills",
]
COPILOT_PROFILE_SOURCE = "copilot_parser_v2"


async def ensure_candidate_profile(
    session: AsyncSession,
    profile: UserProfile,
    *,
    force: bool = False,
    source: str = "profile",
) -> CandidateProfile:
    existing = (
        await session.execute(select(CandidateProfile).where(CandidateProfile.user_id == profile.id).limit(1))
    ).scalar_one_or_none()
    if existing and not force:
        return existing

    resume_text = await current_resume_text(session, profile)
    payload = build_candidate_profile_payload(profile, resume_text)
    if not existing:
        existing = CandidateProfile(user_id=profile.id)
        session.add(existing)

    existing.basics = payload["basics"]
    existing.education = payload["education"]
    existing.experiences = payload["experiences"]
    existing.projects = payload["projects"]
    existing.skills = payload["skills"]
    existing.target_preferences = payload["target_preferences"]
    existing.field_statuses = payload["field_statuses"]
    existing.completeness = payload["completeness"]
    existing.source = source[:60]
    await session.flush()
    return existing


async def ensure_copilot_candidate_profile(session: AsyncSession, profile: UserProfile) -> CandidateProfile:
    existing = (
        await session.execute(select(CandidateProfile).where(CandidateProfile.user_id == profile.id).limit(1))
    ).scalar_one_or_none()
    if existing and existing.source in {"user_confirmed", COPILOT_PROFILE_SOURCE}:
        return existing
    return await ensure_candidate_profile(session, profile, force=True, source=COPILOT_PROFILE_SOURCE)


def build_candidate_profile_payload(profile: UserProfile, resume_text: str) -> dict[str, Any]:
    text = normalize_text(resume_text or profile.resume_text or "")
    basics = {
        "name": profile.name or "同学",
        "target_city": profile.target_city or "",
        "communication_style": profile.communication_style or "温暖直接",
    }
    target_preferences = {
        "role": profile.target_role or "产品经理",
        "company": profile.target_company or "",
        "stage": profile.stage or "投递期",
    }
    education = section_items(text, ["教育背景", "教育经历", "学校", "专业"], "education")
    experiences = section_items(text, ["实习经历", "工作经历", "实践经历"], "experience")
    projects = section_items(text, ["项目经历", "项目经验", "作品经历"], "project")
    skills = extract_skills(text, profile)
    field_statuses = build_field_statuses(basics, target_preferences, education, experiences, projects, skills)
    return {
        "basics": basics,
        "target_preferences": target_preferences,
        "education": education,
        "experiences": experiences,
        "projects": projects,
        "skills": skills,
        "field_statuses": field_statuses,
        "completeness": completeness(field_statuses),
    }


async def current_resume_text(session: AsyncSession, profile: UserProfile) -> str:
    if (profile.resume_text or "").strip():
        return profile.resume_text
    latest = (
        await session.execute(
            select(ResumeVersion)
            .where(ResumeVersion.user_id == profile.id)
            .order_by(desc(ResumeVersion.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    return latest.content if latest else ""


def serialize_candidate_profile(item: CandidateProfile) -> dict[str, Any]:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "basics": item.basics or {},
        "education": item.education or [],
        "experiences": item.experiences or [],
        "projects": item.projects or [],
        "skills": item.skills or [],
        "target_preferences": item.target_preferences or {},
        "field_statuses": item.field_statuses or {},
        "completeness": item.completeness or 0,
        "source": item.source,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def normalize_text(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", str(value or "").replace("\r\n", "\n")).strip()


def section_items(text: str, markers: list[str], item_type: str) -> list[dict[str, str]]:
    excerpt = section_excerpt(text, markers)
    if not excerpt:
        return []
    chunks = split_section_chunks(excerpt, item_type)
    if not chunks:
        chunks = [excerpt]
    return [
        {
            "title": title_from_chunk(chunk, item_type),
            "summary": short_text(chunk, 360),
            "status": "uncertain" if len(chunk) < 40 else "confirmed",
        }
        for chunk in chunks[:4]
    ]


def section_excerpt(text: str, markers: list[str], limit: int = 3200) -> str:
    if not text:
        return ""
    for marker in markers:
        match = re.search(rf"{re.escape(marker)}[:：]?\s*([\s\S]{{0,{limit}}})", text, flags=re.IGNORECASE)
        if match:
            excerpt = match.group(1).strip()
            next_section = re.search(r"\n\s*(教育|实习|工作|项目|技能|竞赛|校园|获奖|自我评价)[^\n]{0,12}[:：]?", excerpt)
            return excerpt[: next_section.start()].strip() if next_section and next_section.start() > 20 else excerpt
    return ""


def split_section_chunks(excerpt: str, item_type: str) -> list[str]:
    lines = [line.strip(" \t") for line in (excerpt or "").splitlines()]
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if not line:
            continue
        if starts_new_item_line(line, item_type):
            if current:
                chunks.append(current)
            current = [line]
            continue
        if current:
            current.append(line)
        else:
            current = [line]
    if current:
        chunks.append(current)
    if len(chunks) <= 1 and "\n" not in excerpt:
        return [chunk.strip(" \n-•") for chunk in re.split(r"\n\s*\n", excerpt) if chunk.strip()]
    return ["\n".join(chunk).strip(" \n-•") for chunk in chunks if "\n".join(chunk).strip(" \n-•")]


def starts_new_item_line(line: str, item_type: str) -> bool:
    clean = line.strip()
    if not clean or clean.startswith(("•", "-", "·")):
        return False
    if re.match(r"^(工作概述|职责|工作内容|项目内容|项目职责|项目成果|成果|亮点|描述|背景|目标|行动|结果|收获)[:：]", clean):
        return False
    if item_type == "experience":
        has_date = bool(re.search(r"20\d{2}(?:[./-]\d{1,2})?", clean))
        has_role = bool(re.search(r"(产品经理|产品实习生|运营|用户研究|数据分析|策略产品|项目助理)", clean, re.I))
        has_separator = bool(re.search(r"\s[-|｜丨—]\s|[-|｜丨—]", clean))
        return len(clean) <= 120 and (has_date or has_separator) and has_role
    if item_type == "project":
        return len(clean) <= 120 and bool(re.search(r"(项目|Agent|系统|平台|工具|增长|商业化|探索|产品)", clean, re.I))
    if item_type == "education":
        return len(clean) <= 140 and bool(re.search(r"(大学|学院|学校|硕士|本科|博士|GPA|专业)", clean))
    return False


def title_from_chunk(chunk: str, fallback: str) -> str:
    line = next((item.strip(" -•") for item in chunk.splitlines() if item.strip()), "")
    cleaned = re.sub(r"\s+", " ", line)
    return short_text(cleaned or fallback, 80)


def extract_skills(text: str, profile: UserProfile) -> list[str]:
    known = [
        "SQL",
        "Python",
        "Excel",
        "Axure",
        "Figma",
        "PRD",
        "用户研究",
        "需求分析",
        "竞品分析",
        "数据分析",
        "AIGC",
        "LLM",
        "RAG",
        "Agent",
    ]
    found = [skill for skill in known if skill.lower() in text.lower()]
    for value in profile.strengths or []:
        if len(found) >= 12:
            break
        token = short_text(value, 24)
        if token and token not in found:
            found.append(token)
    return found[:12]


def build_field_statuses(
    basics: dict[str, Any],
    target_preferences: dict[str, Any],
    education: list[dict],
    experiences: list[dict],
    projects: list[dict],
    skills: list[str],
) -> dict[str, str]:
    statuses = {
        "basics.name": "confirmed" if basics.get("name") and basics.get("name") != "同学" else "missing",
        "target_preferences.role": "confirmed" if target_preferences.get("role") else "missing",
        "target_preferences.company": "confirmed" if target_preferences.get("company") else "uncertain",
        "education": list_status(education),
        "experiences": list_status(experiences),
        "projects": list_status(projects),
        "skills": "confirmed" if len(skills) >= 2 else "uncertain" if skills else "missing",
    }
    return statuses


def list_status(values: list[dict]) -> str:
    if not values:
        return "missing"
    return "confirmed" if any(item.get("status") == "confirmed" for item in values) else "uncertain"


def completeness(field_statuses: dict[str, str]) -> int:
    score = 0.0
    for field in PROFILE_FIELDS:
        status = field_statuses.get(field)
        score += 1 if status == "confirmed" else 0.45 if status == "uncertain" else 0
    return round(score / len(PROFILE_FIELDS) * 100)


def short_text(value: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    return clean if len(clean) <= limit else f"{clean[:limit - 1]}..."
