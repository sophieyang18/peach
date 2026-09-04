from __future__ import annotations

import asyncio
import logging
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
AGENT_PARSE_TIMEOUT_SECONDS = 12
BACKGROUND_AGENT_PARSE_TIMEOUT_SECONDS = 90
logger = logging.getLogger(__name__)


async def ensure_candidate_profile(
    session: AsyncSession,
    profile: UserProfile,
    *,
    force: bool = False,
    source: str = "profile",
    llm_agent: Any | None = None,
    resume_text_override: str | None = None,
    agent_timeout_seconds: float | None = None,
) -> CandidateProfile:
    existing = (
        await session.execute(select(CandidateProfile).where(CandidateProfile.user_id == profile.id).limit(1))
    ).scalar_one_or_none()
    if existing and not force:
        return existing

    resume_text = resume_text_override if resume_text_override is not None else await current_resume_text(session, profile)
    payload = await build_candidate_profile_payload_with_agent(profile, resume_text, llm_agent, timeout_seconds=agent_timeout_seconds)
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


async def build_candidate_profile_payload_with_agent(
    profile: UserProfile,
    resume_text: str,
    llm_agent: Any | None = None,
    *,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    fallback = build_candidate_profile_payload(profile, resume_text)
    if not llm_agent or not normalize_text(resume_text):
        return fallback
    try:
        if hasattr(llm_agent, "get_client") and llm_agent.get_client() is None:
            logger.warning("Candidate profile agent parser skipped because LLM client is not configured")
            return fallback
        data = await asyncio.wait_for(
            llm_agent.extract_candidate_profile(profile, resume_text, fallback),
            timeout=timeout_seconds or AGENT_PARSE_TIMEOUT_SECONDS,
        )
        if not isinstance(data, dict):
            logger.warning("Candidate profile agent parser returned non-object JSON: %s", type(data).__name__)
            return fallback
        if isinstance(data.get("field_statuses"), dict) and data["field_statuses"].get("_parser") == "rules":
            logger.warning("Candidate profile agent parser returned rules fallback payload")
            return fallback
        payload = normalize_candidate_profile_payload(data, fallback)
        if not agent_payload_has_expected_coverage(payload, resume_text):
            return fallback
    except asyncio.TimeoutError:
        logger.warning("Candidate profile agent parser timed out after %.1f seconds", timeout_seconds or AGENT_PARSE_TIMEOUT_SECONDS)
        return fallback
    except Exception:
        logger.exception("Candidate profile agent parser failed")
        return fallback
    payload["field_statuses"]["_parser"] = "agent"
    return payload


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
    field_statuses["_parser"] = "rules"
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


def normalize_candidate_profile_payload(data: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    basics = clean_dict(data.get("basics"), fallback.get("basics", {}), 160)
    target_preferences = clean_dict(data.get("target_preferences"), fallback.get("target_preferences", {}), 180)
    education = normalize_profile_items(data.get("education"), "education", fallback.get("education", []))
    experiences = normalize_profile_items(data.get("experiences"), "experience", fallback.get("experiences", []))
    projects = normalize_profile_items(data.get("projects"), "project", fallback.get("projects", []))
    skills = normalize_skills(data.get("skills"), fallback.get("skills", []))
    field_statuses = data.get("field_statuses") if isinstance(data.get("field_statuses"), dict) else {}
    if not field_statuses:
        field_statuses = build_field_statuses(basics, target_preferences, education, experiences, projects, skills)
    completeness_value = data.get("completeness")
    try:
        completeness_score = int(completeness_value)
    except (TypeError, ValueError):
        completeness_score = completeness(field_statuses)
    return {
        "basics": basics,
        "target_preferences": target_preferences,
        "education": education,
        "experiences": experiences,
        "projects": projects,
        "skills": skills,
        "field_statuses": field_statuses,
        "completeness": max(0, min(100, completeness_score)),
    }


def agent_payload_has_expected_coverage(payload: dict[str, Any], resume_text: str) -> bool:
    expected_education = len(split_section_chunks(section_excerpt(resume_text, ["教育背景", "教育经历"], 8000), "education"))
    expected_experiences = len(split_section_chunks(section_excerpt(resume_text, ["实习经历", "工作经历", "实践经历"], 8000), "experience"))
    expected_projects = len(split_section_chunks(section_excerpt(resume_text, ["项目经历", "项目经验", "作品经历"], 8000), "project"))
    checks = [
        ("education", expected_education, lambda item: item.get("school") or item.get("title")),
        ("experiences", expected_experiences, lambda item: item.get("company") and item.get("role")),
        ("projects", expected_projects, lambda item: item.get("project_name") or item.get("title")),
    ]
    for key, expected, predicate in checks:
        values = payload.get(key) if isinstance(payload.get(key), list) else []
        if expected >= 2 and len(values) < expected:
            logger.warning("Candidate profile agent parser rejected: %s coverage %s/%s", key, len(values), expected)
            return False
        if values and not any(predicate(item) for item in values if isinstance(item, dict)):
            logger.warning("Candidate profile agent parser rejected: %s lacks required fields", key)
            return False
    return True


def clean_dict(value: Any, fallback: dict[str, Any], limit: int) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    result: dict[str, str] = {}
    for key, fallback_value in fallback.items():
        clean = short_text(str(source.get(key) or fallback_value or ""), limit)
        if clean:
            result[str(key)] = clean
    for key, raw in source.items():
        clean = short_text(str(raw or ""), limit)
        if clean and str(key) not in result:
            result[str(key)] = clean
    return result


def normalize_profile_items(value: Any, item_type: str, fallback: list[dict]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return fallback
    values = value
    items: list[dict[str, str]] = []
    for raw in values[:8]:
        if not isinstance(raw, dict):
            continue
        item = normalize_profile_item(raw, item_type)
        if has_meaningful_item_value(item):
            items.append(item)
    return items


def normalize_profile_item(raw: dict[str, Any], item_type: str) -> dict[str, str]:
    if item_type == "experience":
        item = {
            "title": short_text(str(raw.get("title") or ""), 100),
            "company": short_text(str(raw.get("company") or ""), 100),
            "role": short_text(str(raw.get("role") or ""), 100),
            "location": short_text(str(raw.get("location") or ""), 80),
            "start_date": normalize_date_text(raw.get("start_date") or raw.get("start")),
            "end_date": normalize_date_text(raw.get("end_date") or raw.get("end")),
            "summary": short_text(str(raw.get("summary") or raw.get("description") or ""), 900),
            "status": normalize_status(raw.get("status")),
        }
        item["title"] = item["title"] or " ".join(part for part in [item["company"], item["role"]] if part)
        return item
    if item_type == "project":
        item = {
            "title": short_text(str(raw.get("title") or raw.get("project_name") or raw.get("name") or ""), 120),
            "project_name": short_text(str(raw.get("project_name") or raw.get("name") or raw.get("title") or ""), 120),
            "role": short_text(str(raw.get("role") or ""), 100),
            "start_date": normalize_date_text(raw.get("start_date") or raw.get("start")),
            "end_date": normalize_date_text(raw.get("end_date") or raw.get("end")),
            "link": short_text(str(raw.get("link") or raw.get("url") or ""), 240),
            "summary": short_text(str(raw.get("summary") or raw.get("description") or ""), 1000),
            "status": normalize_status(raw.get("status")),
        }
        return item
    item = {
        "title": short_text(str(raw.get("title") or raw.get("school") or raw.get("school_name") or ""), 120),
        "degree": short_text(str(raw.get("degree") or raw.get("education_level") or ""), 80),
        "school": short_text(str(raw.get("school") or raw.get("school_name") or raw.get("title") or ""), 120),
        "college": short_text(str(raw.get("college") or raw.get("department") or ""), 100),
        "major": short_text(str(raw.get("major") or ""), 100),
        "ranking": short_text(str(raw.get("ranking") or raw.get("rank") or ""), 80),
        "gpa_total": short_text(str(raw.get("gpa_total") or raw.get("gpaTotal") or ""), 20),
        "gpa": short_text(str(raw.get("gpa") or ""), 20),
        "advisor": short_text(str(raw.get("advisor") or ""), 80),
        "lab": short_text(str(raw.get("lab") or raw.get("laboratory") or ""), 100),
        "research": short_text(str(raw.get("research") or raw.get("research_direction") or ""), 160),
        "start_date": normalize_date_text(raw.get("start_date") or raw.get("start")),
        "end_date": normalize_date_text(raw.get("end_date") or raw.get("end")),
        "recommended": short_text(str(raw.get("recommended") or ""), 20),
        "scholarship": short_text(str(raw.get("scholarship") or ""), 40),
        "summary": short_text(str(raw.get("summary") or raw.get("description") or ""), 600),
        "status": normalize_status(raw.get("status")),
    }
    return item


def normalize_skills(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    raw_values = value
    skills: list[str] = []
    for raw in raw_values:
        clean = short_text(str(raw or ""), 32)
        if clean and clean not in skills:
            skills.append(clean)
    return skills[:16]


def has_meaningful_item_value(item: dict[str, str]) -> bool:
    return any(str(value or "").strip() for key, value in item.items() if key not in {"status"})


def normalize_status(value: Any) -> str:
    clean = str(value or "").strip().lower()
    if clean in {"confirmed", "uncertain", "missing"}:
        return clean
    return "confirmed"


def normalize_date_text(value: Any) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    clean = clean.replace("/", ".").replace("-", ".")
    clean = re.sub(r"\s+", "", clean)
    if clean in {"现在", "至今", "当前"}:
        return "至今"
    return short_text(clean, 24)


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
    items: list[dict[str, str]] = []
    for chunk in chunks[:4]:
        item = {
            "title": title_from_chunk(chunk, item_type),
            "summary": short_text(chunk, 360),
            "status": "uncertain" if len(chunk) < 40 else "confirmed",
        }
        if item_type == "experience":
            item.update(experience_fields_from_chunk(chunk))
        if item_type == "project":
            item.update(project_fields_from_chunk(chunk))
        if item_type == "education":
            item.update(education_fields_from_chunk(chunk))
        items.append(item)
    return items


SECTION_HEADING_PATTERN = (
    r"(?:教育背景|教育经历|实习经历|工作经历|实践经历|项目经历|项目经验|作品经历|"
    r"个人技能|专业技能|技能|其他|竞赛经历|获奖经历|荣誉经历|校园经历|求职意向|自我评价)"
)


def section_excerpt(text: str, markers: list[str], limit: int = 3200) -> str:
    if not text:
        return ""
    for marker in markers:
        match = re.search(rf"(?:^|\n)\s*{re.escape(marker)}[:：]?\s*([\s\S]{{0,{limit}}})", text, flags=re.IGNORECASE)
        if match:
            excerpt = match.group(1).strip()
            next_section = re.search(rf"\n\s*{SECTION_HEADING_PATTERN}\s*[:：]?\s*(?=\n|$)", excerpt, flags=re.IGNORECASE)
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
        has_date = bool(re.search(r"20\d{2}(?:[./-]\d{1,2})?", clean))
        has_separator = bool(re.search(r"\s[-|｜丨—]\s|[-|｜丨—]", clean))
        has_project_signal = bool(re.search(r"(项目|Agent|系统|平台|工具|增长|商业化|探索|产品)", clean, re.I))
        return len(clean) <= 140 and has_separator and (has_date or has_project_signal)
    if item_type == "education":
        return len(clean) <= 140 and bool(re.search(r"(大学|学院|学校|硕士|本科|博士|GPA|专业)", clean))
    return False


def title_from_chunk(chunk: str, fallback: str) -> str:
    line = next((item.strip(" -•") for item in chunk.splitlines() if item.strip()), "")
    cleaned = re.sub(r"\s+", " ", line)
    return short_text(cleaned or fallback, 80)


def experience_fields_from_chunk(chunk: str) -> dict[str, str]:
    clean = normalize_text(chunk)
    first_line = next((line.strip(" -•") for line in clean.splitlines() if line.strip()), clean)
    dates = [match.group(0).replace(".", "-").replace("/", "-") for match in re.finditer(r"20\d{2}(?:[./-]\d{1,2})?|至今|现在", clean)]
    role = first_regex_group(
        clean,
        r"(AI\s*产品经理|AIGC\s*策略产品经理|AIGC\s*产品经理|策略产品经理|产品经理|产品实习生|产品运营|用户研究|数据分析|项目助理|[\u4e00-\u9fa5A-Za-z0-9]{0,12}实习生|PM)",
    )
    company = infer_experience_company(first_line, role)
    description = "\n".join(line for line in clean.splitlines() if line.strip() and line.strip() != first_line).strip() or clean
    return {
        "company": short_text(company, 80),
        "role": short_text(role, 80),
        "start_date": dates[0] if dates else "",
        "end_date": dates[1] if len(dates) > 1 else "",
        "description": short_text(description, 600),
    }


def infer_experience_company(line: str, role: str) -> str:
    before_role = line.split(role)[0] if role and role in line else line
    clean = re.sub(r"20\d{2}(?:[./-]\d{1,2})?", " ", before_role)
    clean = re.sub(r"[|｜丨—–-]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    known = first_regex_group(
        clean,
        r"(字节跳动|快手|百度|腾讯|阿里巴巴|阿里|美团|小红书|京东|网易|华为|[\u4e00-\u9fa5A-Za-z0-9]{2,24}(?:公司|集团|科技|平台))",
    )
    return known or (clean.split(" ")[0] if clean else "")


def project_fields_from_chunk(chunk: str) -> dict[str, str]:
    clean = normalize_text(chunk)
    first_line = next((line.strip(" -•") for line in clean.splitlines() if line.strip()), clean)
    dates = [match.group(0).replace(".", "-").replace("/", "-") for match in re.finditer(r"20\d{2}(?:[./-]\d{1,2})?|至今|现在", clean)]
    role = first_regex_group(
        clean,
        r"(独立产品负责人|产品负责人|项目负责人|运营负责人|负责人|产品经理|PM|核心成员|组长|队长|研发|设计|策划)",
    )
    link = first_regex_group(clean, r"(https?://[^\s，。；)）]+|www\.[^\s，。；)）]+)")
    project_name = infer_project_name(first_line, role)
    description = "\n".join(line for line in clean.splitlines() if line.strip() and line.strip() != first_line).strip() or clean
    return {
        "project_name": short_text(project_name, 100),
        "role": short_text(role, 80),
        "start_date": dates[0] if dates else "",
        "end_date": dates[1] if len(dates) > 1 else "",
        "link": short_text(link, 240),
        "description": short_text(description, 700),
    }


def infer_project_name(line: str, role: str) -> str:
    before_role = line.split(role)[0] if role and role in line else line
    clean = re.sub(r"https?://\S+|www\.\S+", " ", before_role)
    clean = re.sub(r"20\d{2}(?:[./-]\d{1,2})?", " ", clean)
    clean = re.sub(r"[|｜丨—–-]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    known = first_regex_group(
        clean,
        r"([\u4e00-\u9fa5A-Za-z0-9]{2,40}(?:项目|Agent|平台|系统|工具|增长|商业化|探索))",
    )
    return known or clean


def education_fields_from_chunk(chunk: str) -> dict[str, str]:
    clean = normalize_text(chunk)
    dates = [match.group(0).replace(".", "-").replace("/", "-") for match in re.finditer(r"20\d{2}(?:[./-]\d{1,2})?|至今|现在", clean)]
    gpa_match = re.search(r"GPA[：:\s]*([0-9](?:\.\d+)?)(?:\s*[/／]\s*([0-9](?:\.\d+)?))?", clean, flags=re.I)
    return {
        "degree": infer_education_degree(clean),
        "school": short_text(infer_school_name(clean), 100),
        "college": short_text(first_regex_group(clean, r"([\u4e00-\u9fa5A-Za-z0-9]{2,30}(?:学院|学部|院系|系))"), 80),
        "major": short_text(infer_major(clean), 80),
        "ranking": short_text(first_regex_group(clean, r"(前\s*\d+%|排名\s*[:：]?\s*[^\s，。；|｜]+)"), 40),
        "gpa_total": gpa_match.group(2).strip() if gpa_match and gpa_match.group(2) else "",
        "gpa": gpa_match.group(1).strip() if gpa_match else "",
        "advisor": short_text(first_regex_group(clean, r"导师[:：\s]*([^\n，。；|｜]+)"), 80),
        "lab": short_text(first_regex_group(clean, r"([\u4e00-\u9fa5A-Za-z0-9]{2,30}(?:实验室|研究中心))"), 80),
        "research": short_text(first_regex_group(clean, r"研究方向[:：\s]*([^\n，。；|｜]+)"), 120),
        "start_date": dates[0] if dates else "",
        "end_date": dates[1] if len(dates) > 1 else "",
        "recommended": "是" if re.search(r"保送|推免", clean) else "",
        "scholarship": "是" if "国家奖学金" in clean else "",
    }


def infer_education_degree(value: str) -> str:
    if "博士" in value:
        return "博士"
    if "硕士" in value or "研究生" in value:
        return "硕士"
    if "本科" in value or "学士" in value:
        return "本科"
    if "大专" in value or "专科" in value:
        return "大专"
    if "高中" in value:
        return "高中"
    return ""


def infer_school_name(value: str) -> str:
    school = first_regex_group(value, r"([\u4e00-\u9fa5A-Za-z0-9·.\-\s]{2,40}(?:大学|学院|学校|University|College))")
    return re.sub(r"\s+", " ", school).strip()


def infer_major(value: str) -> str:
    explicit = first_regex_group(value, r"(?:专业|主修)(?:为|是|方向)?[:：]\s*([^\n，。；|｜]+)")
    if not explicit:
        explicit = first_regex_group(value, r"(?:专业|主修)(?:为|是)\s*([^\n，。；|｜]+)")
    if explicit:
        return explicit
    first_line = next((line.strip() for line in normalize_text(value).splitlines() if line.strip()), value)
    after_school = re.search(r"(?:大学|学院|学校)\s*[-—–]\s*([^（(GPA\n]+)", first_line)
    if after_school:
        return after_school.group(1).strip()
    match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{2,24}(?:专业|学|工程|管理|语言|文学|经济|金融|计算机|法语|英语))", value)
    return match.group(1).removesuffix("专业").strip() if match else ""


def first_regex_group(value: str, pattern: str) -> str:
    match = re.search(pattern, value, flags=re.I)
    return match.group(1).strip() if match else ""


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
