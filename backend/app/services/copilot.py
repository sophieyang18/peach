from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from backend.app.models import CandidateProfile, UserProfile


SENSITIVE_FIELD_RE = re.compile(r"(password|passwd|pwd|captcha|验证码|校验码|短信码|hidden|token|csrf)", re.I)
OPEN_QUESTION_RE = re.compile(r"(开放题|问答|为什么|介绍|优势|规划|项目|经历|困难|挑战|理解|看法|动机|reason|essay|answer|question)", re.I)
QUESTION_DRAFT_FIELD_RE = re.compile(r"(为什么|原因|动机|申请理由|选择|优势|规划|困难|挑战|理解|看法|开放题|问答|essay|answer|question)", re.I)
CORE_DRAFT_FIELD_RE = re.compile(
    r"(实习内容|实习描述|工作内容|工作职责|岗位职责|职责描述|单位介绍|公司介绍|"
    r"项目描述|项目内容|项目经历|项目经验|实践内容|实践经历|自我评价|个人评价|"
    r"论文|专著|研究内容)",
    re.I,
)
CONFIDENCE_THRESHOLD = 0.72
ROLE_TOKEN_RE = re.compile(
    r"(AIGC策略产品经理|AI产品经理|产品经理|产品实习生|策略产品|产品运营|运营实习生|项目助理|数据分析|用户研究)",
    re.I,
)
ORG_STOPWORD_RE = re.compile(r"(通过|负责|主导|协同|推动|实现|提高|降低|工作概述|链路|评测|合作|业务|工具|流程|方案|策略)")

FIELD_RULES: list[tuple[str, str, list[str]]] = [
    ("basics.name", "姓名", ["姓名", "名字", "真实姓名", "name", "full name"]),
    ("basics.gender", "性别", ["性别", "gender"]),
    ("basics.birth_date", "出生日期", ["出生日期", "生日", "年龄", "birth date", "birthday"]),
    ("basics.phone", "手机", ["手机", "电话", "联系电话", "手机号", "phone", "mobile", "tel"]),
    ("basics.email", "邮箱", ["邮箱", "邮件", "email", "e-mail", "mail"]),
    ("basics.id_number", "证件号码", ["证件号码", "身份证号", "证件号", "id number", "identity"]),
    ("basics.hometown", "籍贯", ["籍贯", "户籍", "生源地", "hometown", "domicile"]),
    ("basics.current_residence", "现居住地", ["现居住地", "现居地", "居住地", "当前城市", "current residence"]),
    ("basics.marital_status", "婚姻状况", ["婚姻", "婚否", "marital"]),
    ("basics.political_status", "政治面貌", ["政治面貌", "政治身份", "political"]),
    ("basics.overseas_experience", "海外留学经历", ["海外留学经历", "留学经历", "海外经历", "overseas"]),
    ("basics.application_type", "应届/往届", ["应届", "往届", "应届/往届", "应届往届", "毕业生类型"]),
    ("basics.professional_title", "专业技术职称", ["专业技术职称", "职称", "技术职称"]),
    ("basics.english_level", "英语等级", ["英语等级", "英语水平", "外语等级", "外语水平", "english level"]),
    ("basics.source_channel", "了解渠道", ["了解渠道", "主要渠道", "招聘渠道", "来源渠道", "source channel"]),
    ("basics.self_evaluation", "自我评价", ["自我评价", "个人评价", "自我描述", "self evaluation"]),
    ("education.0.school", "学校", ["学校", "学校名称", "院校", "毕业院校", "大学", "school", "university"]),
    ("education.0.degree", "学历/学位", ["学历", "最高学历", "学位", "最高学位", "degree", "education level"]),
    ("education.0.degree_type", "硕士学位类型", ["硕士学位类型", "研究生类型", "硕士类型", "培养方式"]),
    ("education.0.enrollment_year", "入学年份", ["入学年份", "入学时间", "enrollment", "enroll"]),
    ("education.0.major", "专业", ["专业", "major"]),
    ("education.0.start_date", "入学时间", ["入学", "入校", "start date"]),
    ("education.0.end_date", "毕业时间", ["毕业", "graduate"]),
    ("experiences.0.company", "实习单位", ["实习单位", "单位名称", "工作单位", "公司名称", "employer"]),
    ("experiences.0.role", "实习岗位", ["实习岗位", "职位名称", "职务", "岗位名称", "job title"]),
    ("experiences.0.location", "实习地点", ["实习地点", "工作地点", "工作城市", "location"]),
    ("experiences.0.start_date", "实习开始时间", ["实习开始时间", "工作开始时间", "任职开始时间"]),
    ("experiences.0.end_date", "实习结束时间", ["实习结束时间", "工作结束时间", "任职结束时间"]),
    ("target_preferences.company", "目标公司", ["目标公司", "应聘公司", "公司", "company"]),
    ("target_preferences.role", "目标岗位", ["目标岗位", "应聘岗位", "岗位", "职位", "role", "position", "job"]),
    ("target_preferences.career_objective", "职业目标", ["职业目标", "职业规划", "求职目标", "求职意向", "career objective"]),
    ("experiences.0.summary", "实习描述", ["实习内容", "实习描述", "实习经历", "工作内容", "工作经历", "工作描述", "工作职责", "职责描述", "岗位职责", "internship", "work experience"]),
    ("projects.0.title", "项目名称", ["项目名称", "项目标题", "project name"]),
    ("projects.0.summary", "项目描述", ["项目描述", "项目内容", "项目经历", "项目经验", "project description"]),
    ("awards.0.title", "奖项名称", ["奖项名称", "获奖名称", "荣誉名称", "竞赛名称", "奖励名称"]),
    ("awards.0.summary", "获奖描述", ["获奖描述", "获奖经历", "荣誉经历", "竞赛经历", "奖项描述", "奖励描述"]),
    ("awards", "奖项", ["奖项", "获奖", "荣誉", "奖励", "award", "honor"]),
    ("skills", "技能", ["技能", "能力", "工具", "技术栈", "skills"]),
]


@dataclass
class CandidateSnapshot:
    values: dict[str, str]
    completeness: int
    sections: dict[str, list[dict[str, str]]]


def build_candidate_snapshot(profile: UserProfile, candidate: CandidateProfile) -> CandidateSnapshot:
    basics = candidate.basics or {}
    target = candidate.target_preferences or {}
    resume_text = profile.resume_text or ""
    education_items = [build_education_values(item, resume_text) for item in list_items(candidate.education)[:4]]
    experience_items = [build_experience_values(item) for item in list_items(candidate.experiences)[:4]]
    project_items = [build_project_values(item) for item in list_items(candidate.projects)[:4]]
    award_items = extract_award_items(resume_text)
    education = first_item(education_items)
    experience = first_item(experience_items)
    project = first_item(project_items)
    values = {
        "basics.name": str(basics.get("name") or profile.name or ""),
        "basics.gender": clean_value(str(basics.get("gender") or "")),
        "basics.birth_date": clean_value(str(basics.get("birth_date") or "")),
        "basics.phone": extract_phone(resume_text),
        "basics.email": extract_email(resume_text),
        "basics.id_number": clean_value(str(basics.get("id_number") or "")),
        "basics.hometown": clean_value(str(basics.get("hometown") or "")),
        "basics.current_residence": clean_value(str(basics.get("current_residence") or "")) or extract_current_residence(resume_text),
        "basics.marital_status": clean_value(str(basics.get("marital_status") or "")),
        "basics.political_status": clean_value(str(basics.get("political_status") or "")) or extract_political_status(resume_text),
        "basics.overseas_experience": clean_value(str(basics.get("overseas_experience") or "")) or extract_overseas_experience(resume_text),
        "basics.application_type": clean_value(str(basics.get("application_type") or "")) or extract_application_type(resume_text, education.get("end_date", "")),
        "basics.professional_title": clean_value(str(basics.get("professional_title") or "")) or extract_professional_title(resume_text),
        "basics.english_level": clean_value(str(basics.get("english_level") or "")) or extract_english_level(resume_text),
        "basics.source_channel": clean_value(str(basics.get("source_channel") or "")),
        "basics.self_evaluation": clean_value(str(basics.get("self_evaluation") or "")),
        "education.0.school": education.get("school", ""),
        "education.0.degree": education.get("degree", ""),
        "education.0.degree_type": education.get("degree_type", ""),
        "education.0.major": education.get("major", ""),
        "education.0.enrollment_year": education.get("start_date", ""),
        "education.0.start_date": education.get("start_date", ""),
        "education.0.end_date": education.get("end_date", ""),
        "experiences.0.company": experience.get("company", ""),
        "experiences.0.role": experience.get("role", ""),
        "experiences.0.location": experience.get("location", ""),
        "experiences.0.start_date": experience.get("start_date", ""),
        "experiences.0.end_date": experience.get("end_date", ""),
        "target_preferences.company": str(target.get("company") or profile.target_company or ""),
        "target_preferences.role": str(target.get("role") or profile.target_role or ""),
        "target_preferences.career_objective": build_career_objective(profile, candidate),
        "experiences.0.summary": str(experience.get("summary") or ""),
        "projects.0.title": str(project.get("title") or ""),
        "projects.0.summary": str(project.get("summary") or ""),
        "awards.0.title": award_items[0].get("title", "") if award_items else "",
        "awards.0.summary": award_items[0].get("summary", "") if award_items else "",
        "awards": extract_awards(resume_text),
        "skills": "、".join(candidate.skills or []),
    }
    sections = {
        "education": education_items,
        "experiences": experience_items,
        "projects": project_items,
        "awards": award_items,
    }
    for section, items in sections.items():
        for index, item in enumerate(items):
            for key, value in item.items():
                values[f"{section}.{index}.{key}"] = value
    return CandidateSnapshot(
        values={key: clean_value(value) for key, value in values.items()},
        completeness=candidate.completeness or 0,
        sections=sections,
    )


def map_form_fields(
    fields: list[dict[str, Any]],
    snapshot: CandidateSnapshot,
    *,
    url: str = "",
    repeaters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    safe_fields = [normalize_field(field) for field in fields if not is_sensitive_field(field)]
    mappings = [map_one_field(field, snapshot) for field in safe_fields]
    repeat_actions = expand_repeatable_mappings(mappings, snapshot, normalize_repeaters(repeaters or []))
    preview = build_preview(url, fields, safe_fields, mappings)
    preview["repeat_actions"] = repeat_actions
    return preview


def refresh_repeat_actions(
    preview: dict[str, Any],
    snapshot: CandidateSnapshot,
    repeaters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    base_mappings = [
        item
        for item in preview.get("mappings", [])
        if item.get("mapping_type") != "repeat_expanded"
    ]
    preview["mappings"] = base_mappings
    preview["repeat_actions"] = expand_repeatable_mappings(base_mappings, snapshot, normalize_repeaters(repeaters or []))
    preview["summary"] = summarize_mappings(preview.get("mappings", []))
    return preview


def build_preview(url: str, raw_fields: list[dict[str, Any]], safe_fields: list[dict[str, Any]], mappings: list[dict[str, Any]]) -> dict[str, Any]:
    direct = len([item for item in mappings if item["status"] == "autofilled"])
    ai = len([item for item in mappings if item["status"] == "ai_generated"])
    needs = len([item for item in mappings if item["status"] == "needs_confirmation"])
    return {
        "url": url,
        "field_count": len(safe_fields),
        "skipped_count": max(0, len(raw_fields) - len(safe_fields)),
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "summary": {
            "direct_fill": direct,
            "ai_assisted": ai,
            "needs_confirmation": needs,
            "unsupported": len(safe_fields) - direct - ai - needs,
        },
        "mappings": mappings,
    }


def expand_repeatable_mappings(
    mappings: list[dict[str, Any]],
    snapshot: CandidateSnapshot,
    repeaters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    assign_existing_repeat_indices(mappings, snapshot)
    repeat_actions: list[dict[str, Any]] = []
    for section in ["experiences", "projects", "education", "awards"]:
        items = snapshot.sections.get(section, [])
        if len(items) <= 1:
            continue
        templates = [
            item
            for item in mappings
            if repeated_path_parts(item.get("candidate_path", ""))[0] == section
            and repeated_path_parts(item.get("candidate_path", ""))[1] == 0
        ]
        if not templates:
            continue
        repeater = best_repeater_for_section(repeaters, section)
        if not repeater:
            continue
        repeat_actions.append(
            {
                "section": section,
                "selector": repeater.get("selector", ""),
                "times": max(0, min(len(items) - 1, 3)),
                "label": repeater.get("label", ""),
                "reason": f"检测到 {len(items)} 段{section_label(section)}，需要先新增 {len(items) - 1} 个填写区块。",
            }
        )
        for index in range(1, min(len(items), 4)):
            for template in templates:
                _section, _template_index, field_key = repeated_path_parts(template.get("candidate_path", ""))
                path = f"{section}.{index}.{field_key}"
                value = snapshot.values.get(path, "")
                if not value:
                    continue
                duplicate = {
                    **template,
                    "field_id": f"{template.get('field_id')}_repeat_{index}",
                    "selector": "",
                    "candidate_path": path,
                    "value": value,
                    "confidence": min(0.88, float(template.get("confidence") or 0.78)),
                    "status": "needs_confirmation",
                    "mapping_type": "repeat_expanded",
                    "reason": f"来自第 {index + 1} 段{section_label(section)}，需要新增区块后确认填写。",
                    "repeat_section": section,
                    "repeat_index": index,
                    "field_key": field_key,
                    "resolve": {
                        "section": section,
                        "field_key": field_key,
                        "repeat_index": index,
                        "aliases": aliases_for_repeated_field(section, field_key),
                    },
                }
                mappings.append(duplicate)
    return repeat_actions


def assign_existing_repeat_indices(mappings: list[dict[str, Any]], snapshot: CandidateSnapshot) -> None:
    counters: dict[tuple[str, str, str], int] = {}
    for item in mappings:
        section, index, field_key = repeated_path_parts(item.get("candidate_path", ""))
        if not section or index != 0:
            continue
        counter_key = repeat_counter_key(item, section, field_key)
        occurrence = counters.get(counter_key, 0)
        counters[counter_key] = occurrence + 1
        path = f"{section}.{occurrence}.{field_key}"
        value = snapshot.values.get(path, "")
        if item.get("status") == "ai_generated":
            item.update(
                {
                    "candidate_path": path,
                    "candidate_label": label_for_path(path),
                    "value": "",
                    "repeat_section": section,
                    "repeat_index": occurrence,
                    "field_key": field_key,
                    "draft_source_path": path,
                }
            )
        elif occurrence and value:
            item.update(
                {
                    "candidate_path": path,
                    "candidate_label": label_for_path(path),
                    "value": value,
                    "status": "autofilled" if float(item.get("confidence") or 0) >= CONFIDENCE_THRESHOLD else "needs_confirmation",
                    "mapping_type": "repeat_existing",
                    "repeat_section": section,
                    "repeat_index": occurrence,
                    "field_key": field_key,
                }
            )
        elif value:
            item.update({"repeat_section": section, "repeat_index": occurrence, "field_key": field_key})


def repeat_counter_key(item: dict[str, Any], section: str, field_key: str) -> tuple[str, str, str]:
    label = normalize_match_text(str(item.get("label") or item.get("field", {}).get("label") or item.get("candidate_label") or ""))
    return section, field_key, label or field_key


def label_for_path(path: str) -> str:
    section, index, field_key = repeated_path_parts(path)
    if not section:
        return {rule_path: label for rule_path, label, _aliases in FIELD_RULES}.get(path, path)
    return f"第 {index + 1} 段{section_label(section)} · {field_key_label(section, field_key)}"


def field_key_label(section: str, field_key: str) -> str:
    labels = {
        "experiences": {
            "company": "单位",
            "role": "岗位",
            "location": "地点",
            "start_date": "开始时间",
            "end_date": "结束时间",
            "summary": "内容",
        },
        "projects": {"title": "名称", "summary": "内容"},
        "education": {
            "school": "学校",
            "degree": "学历/学位",
            "degree_type": "学位类型",
            "major": "专业",
            "start_date": "开始时间",
            "end_date": "结束时间",
        },
        "awards": {"title": "名称", "summary": "描述"},
    }
    return labels.get(section, {}).get(field_key, field_key)


def normalize_repeaters(repeaters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(item.get("id") or ""),
            "label": str(item.get("label") or ""),
            "selector": str(item.get("selector") or ""),
            "section": str(item.get("section") or ""),
            "nearbyText": str(item.get("nearbyText") or ""),
        }
        for item in repeaters
        if item.get("selector")
    ]


def best_repeater_for_section(repeaters: list[dict[str, Any]], section: str) -> dict[str, Any] | None:
    return next((item for item in repeaters if item.get("section") == section), None)


def repeated_path_parts(path: str) -> tuple[str, int, str]:
    match = re.match(r"^(experiences|projects|education|awards)\.(\d+)\.([a-z_]+)$", str(path or ""))
    if not match:
        return "", -1, ""
    return match.group(1), int(match.group(2)), match.group(3)


def aliases_for_repeated_field(section: str, field_key: str) -> list[str]:
    aliases = {
        "experiences": {
            "company": ["实习单位", "工作单位", "公司名称", "单位名称", "公司"],
            "role": ["实习岗位", "职位名称", "职务", "岗位名称", "岗位"],
            "location": ["实习地点", "工作地点", "工作城市", "地点"],
            "start_date": ["实习开始时间", "工作开始时间", "任职开始时间", "开始时间"],
            "end_date": ["实习结束时间", "工作结束时间", "任职结束时间", "结束时间"],
            "summary": ["实习内容", "实习描述", "工作内容", "职责描述", "工作职责"],
        },
        "projects": {
            "title": ["项目名称", "项目"],
            "summary": ["项目描述", "项目内容", "项目经历", "项目经验"],
        },
        "education": {
            "school": ["学校", "院校", "毕业院校"],
            "degree": ["学历", "学位"],
            "major": ["专业"],
            "start_date": ["入学时间", "入学年份", "开始时间"],
            "end_date": ["毕业时间", "毕业年份", "结束时间"],
        },
        "awards": {
            "title": ["奖项名称", "获奖名称", "荣誉名称", "竞赛名称", "奖励名称", "奖项"],
            "summary": ["获奖描述", "获奖经历", "荣誉经历", "竞赛经历", "奖项描述", "奖励描述"],
        },
    }
    return aliases.get(section, {}).get(field_key, [field_key])


def section_label(section: str) -> str:
    return {"experiences": "实习/工作经历", "projects": "项目经历", "education": "教育经历", "awards": "获奖经历"}.get(section, section)


async def refine_mappings_with_agent(
    preview: dict[str, Any],
    snapshot: CandidateSnapshot,
    agent: Any,
    *,
    domain: str = "",
) -> dict[str, Any]:
    if not getattr(agent, "get_client", lambda: None)():
        preview["agent_status"] = "not_configured"
        return preview

    candidates = [
        item
        for item in preview.get("mappings", [])
        if item.get("mapping_type") != "repeat_expanded"
    ][:40]
    if not candidates:
        preview["agent_status"] = "not_needed"
        return preview

    available_values = [
        {"path": path, "value": value[:180]}
        for path, value in snapshot.values.items()
        if value
    ]
    if not available_values:
        preview["agent_status"] = "no_profile_values"
        return preview

    fallback = {"mappings": []}
    prompt = f"""
你是桃子的网申表单字段映射 Agent。请基于字段标题、placeholder、name、字段类型、选项和附近文本，判断招聘网站字段应该对应候选人个人资料里的哪个字段。规则映射只是初始候选，最终以你的判断为准。

要求：
1. 只能从 available_values 的 path 中选择 candidate_path，不允许编造候选人资料。
2. 如果字段是自我评价、实习内容、项目描述、申请理由等长文本，candidate_path 可填 open_question。
3. 如果字段是验证码、密码、证件上传、复杂下拉选择、无法确定字段，candidate_path 填空字符串。
4. 如果页面有多个实习/项目/教育/获奖区块，请按页面出现顺序映射到对应资料序号，例如第 1 个项目区块用 projects.0，第 2 个项目区块用 projects.1；不要把多个重复区块都映射到 .0。
5. 相似但不确定时 confidence 不要超过 0.74，前端会要求用户确认。
6. 请尽量为 fields 中每个字段输出一条结果；无法填写也要输出空 candidate_path 并说明原因。
7. 只输出 JSON：{{"mappings":[{{"field_id":"...","candidate_path":"...","confidence":0.0,"reason":"..."}}]}}

招聘域名：{domain or "未知"}
候选人结构化资料：{snapshot_profile_context(snapshot)}
available_values：{available_values}
fields：{[
        {
            "field_id": item.get("field_id"),
            "selector": item.get("selector"),
            "label": item.get("label"),
            "field": item.get("field"),
            "initial_candidate_path": item.get("candidate_path"),
            "initial_confidence": item.get("confidence"),
            "initial_status": item.get("status"),
            "initial_reason": item.get("reason"),
        }
        for item in candidates
    ]}
"""
    try:
        data = await agent.json_complete([{"role": "user", "content": prompt}], fallback, allow_fallback=True)
    except Exception:
        preview["agent_status"] = "failed"
        return preview

    by_field_id = {item.get("field_id"): item for item in preview.get("mappings", [])}
    label_by_path = {path: label for path, label, _aliases in FIELD_RULES}
    refined_count = 0
    decided_count = 0
    for refined in data.get("mappings", []) if isinstance(data, dict) else []:
        field_id = str(refined.get("field_id") or "")
        item = by_field_id.get(field_id)
        if not item:
            continue
        if item.get("mapping_type") == "repeat_expanded":
            continue
        path = str(refined.get("candidate_path") or "")
        confidence = clamp_confidence(refined.get("confidence"))
        if not path:
            if confidence >= 0.45:
                item.update(
                    {
                        "candidate_path": "",
                        "candidate_label": "",
                        "value": "",
                        "confidence": round(confidence, 2),
                        "status": "unsupported",
                        "mapping_type": "agent_decided",
                        "reason": str(refined.get("reason") or "Agent 判断该字段不适合自动填写。")[:160],
                    }
                )
                decided_count += 1
            continue
        if path == "open_question":
            existing_section, _existing_index, _existing_key = repeated_path_parts(item.get("candidate_path", ""))
            draft_path = item.get("candidate_path") if existing_section else "open_question"
            item.update(
                {
                    "candidate_path": draft_path,
                    "candidate_label": label_for_path(draft_path) if existing_section else "桃子 Agent 草稿",
                    "value": "",
                    "confidence": max(0.76, confidence),
                    "status": "ai_generated",
                    "mapping_type": "agent_decided",
                    "draft_source_path": draft_path if existing_section else "",
                    "reason": str(refined.get("reason") or "Agent 判断为需要生成长文本草稿的字段。")[:160],
                }
            )
            refined_count += 1
            decided_count += 1
            continue
        value = snapshot.values.get(path, "")
        if not value:
            continue
        if confidence < 0.45:
            continue
        item.update(
            {
                "candidate_path": path,
                "candidate_label": label_for_path(path),
                "value": "" if item.get("status") == "ai_generated" else value,
                "confidence": round(confidence, 2),
                "status": "ai_generated" if item.get("status") == "ai_generated" else "autofilled" if confidence >= CONFIDENCE_THRESHOLD else "needs_confirmation",
                "mapping_type": "agent_decided",
                "draft_source_path": path if item.get("status") == "ai_generated" else "",
                "reason": str(refined.get("reason") or "Agent 基于字段结构和个人资料决定了映射。")[:160],
            }
        )
        refined_count += 1
        decided_count += 1

    preview["summary"] = summarize_mappings(preview.get("mappings", []))
    preview["agent_status"] = "decided" if decided_count else "no_change"
    preview["agent_refined_count"] = refined_count
    preview["agent_decided_count"] = decided_count
    return preview


def map_one_field(field: dict[str, Any], snapshot: CandidateSnapshot) -> dict[str, Any]:
    if is_custom_picker_field(field):
        return unsupported_mapping(field, "疑似自定义下拉/组合选择器，当前 MVP 为安全起见不自动填写。")

    primary_text = primary_field_text(field)
    text = primary_text or safe_nearby_text(field)
    if is_question_draft_field(field, text):
        return agent_draft_mapping(field, text, snapshot)

    best_path = ""
    best_label = ""
    best_score = 0.0
    for path, label, aliases in FIELD_RULES:
        score = max(match_score(text, alias) for alias in aliases)
        if score > best_score:
            best_path, best_label, best_score = path, label, score

    value = snapshot.values.get(best_path, "")
    if is_core_draft_field(field, text) and not value:
        return agent_draft_mapping(field, text, snapshot)
    if best_score < CONFIDENCE_THRESHOLD and is_core_draft_field(field, text):
        return agent_draft_mapping(field, text, snapshot)
    if not primary_text and field.get("tagName") == "input":
        status = "unsupported"
    elif best_score >= 0.9 and value:
        status = "autofilled"
    elif best_score >= CONFIDENCE_THRESHOLD:
        status = "needs_confirmation" if not value else "autofilled"
    elif best_score >= 0.46 and value:
        status = "needs_confirmation"
    else:
        status = "unsupported"

    return base_mapping(field) | {
        "candidate_path": best_path if status != "unsupported" else "",
        "candidate_label": best_label if status != "unsupported" else "",
        "value": value if status in {"autofilled", "needs_confirmation"} else "",
        "confidence": round(best_score, 2),
        "status": status,
        "mapping_type": "deterministic" if best_score >= CONFIDENCE_THRESHOLD else "semantic_fallback",
        "reason": build_reason(status, best_label, bool(value)),
    }


def summarize_mappings(mappings: list[dict[str, Any]]) -> dict[str, int]:
    direct = len([item for item in mappings if item["status"] == "autofilled"])
    ai = len([item for item in mappings if item["status"] == "ai_generated"])
    needs = len([item for item in mappings if item["status"] == "needs_confirmation"])
    return {
        "direct_fill": direct,
        "ai_assisted": ai,
        "needs_confirmation": needs,
        "unsupported": max(0, len(mappings) - direct - ai - needs),
    }


def clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if number > 1:
        number = number / 100
    return max(0.0, min(0.99, number))


def generate_open_answer(
    question: str,
    jd: str,
    snapshot: CandidateSnapshot,
    *,
    candidate_path: str = "",
    limit: int = 520,
) -> dict[str, Any]:
    role = snapshot.values.get("target_preferences.role") or "目标岗位"
    focus = focus_context(candidate_path, snapshot)
    experience = focus.get("summary") if focus.get("section") == "experiences" else snapshot.values.get("experiences.0.summary")
    project = focus.get("summary") if focus.get("section") == "projects" else snapshot.values.get("projects.0.summary")
    evidence = experience or project
    skills = snapshot.values.get("skills")
    jd_hint = clean_value(jd)[:140]
    if not evidence:
        answer = f"我希望申请{role}，目前已围绕产品分析、需求拆解和结构化表达做准备。后续我会结合岗位要求补充更具体的项目证据。"
    elif re.search(r"(单位介绍|公司介绍)", question):
        org = focus.get("company") if focus.get("section") == "experiences" else snapshot.values.get("experiences.0.company")
        org = org or "该单位"
        answer = (
            f"{org}是我过往经历中的实践场景。"
            f"这段经历主要围绕{experience[:180] if experience else evidence[:180]}展开，"
            f"我主要从自身承担的工作出发理解其业务环境，包括需求沟通、方案推进和结果复盘。"
        )
    elif re.search(r"(实习内容|实习描述|工作内容|工作职责|职责描述|岗位职责)", question):
        answer = (
            f"在这段实习中，我主要围绕{experience[:220] if experience else evidence[:220]}推进工作。"
            f"我重点负责需求拆解、资料整理、方案表达和结果复盘，并在过程中把业务目标转化为可执行任务。"
        )
    elif re.search(r"(项目描述|项目内容|项目经历|项目经验|实践内容|实践经历)", question):
        answer = (
            f"我参与的代表性项目是：{project[:240] if project else evidence[:240]}。"
            f"项目中我主要负责从用户问题出发梳理目标、拆解方案，并结合反馈或数据验证结果。"
        )
    elif re.search(r"(为什么|动机|申请|选择)", question):
        answer = (
            f"我申请{role}主要是因为过往经历和岗位要求有比较明确的交集。"
            f"在经历中，我重点做过：{evidence[:180]}。"
            f"这让我对用户问题拆解、方案取舍和结果复盘有了直接训练。"
        )
    else:
        answer = (
            f"结合我的经历，我会从问题背景、我的动作和结果三个部分回答。"
            f"代表性经历是：{evidence[:220]}。"
            f"其中我主要负责把模糊需求转成可执行方案，并通过数据或用户反馈验证效果。"
        )
    if skills:
        answer += f" 我常用的能力和工具包括：{skills[:120]}。"
    if jd_hint:
        answer += f" 结合这份 JD，我会重点强调与「{jd_hint}」相关的匹配点。"
    return {
        "answer": answer[:limit],
        "needs_review": True,
        "source": "candidate_profile_resume_jd",
        "safety_note": "开放题草稿需要用户确认和编辑后再填写。",
    }


def snapshot_profile_context(snapshot: CandidateSnapshot) -> dict[str, Any]:
    return {
        "basics": {
            key.split(".", 1)[1]: value
            for key, value in snapshot.values.items()
            if key.startswith("basics.") and value
        },
        "target_preferences": {
            key.split(".", 1)[1]: value
            for key, value in snapshot.values.items()
            if key.startswith("target_preferences.") and value
        },
        "education": snapshot.sections.get("education", [])[:4],
        "experiences": snapshot.sections.get("experiences", [])[:4],
        "projects": snapshot.sections.get("projects", [])[:4],
        "awards": snapshot.sections.get("awards", [])[:4],
        "skills": snapshot.values.get("skills", ""),
    }


def format_section_for_prompt(items: list[dict[str, str]]) -> str:
    lines = []
    for index, item in enumerate(items[:4], start=1):
        title = item.get("title") or item.get("company") or item.get("school") or f"第{index}段"
        summary = item.get("summary") or ""
        dates = "-".join(part for part in [item.get("start_date"), item.get("end_date")] if part)
        lines.append(f"{index}. {title} {dates} {summary}".strip())
    return "\n".join(lines)


def focus_context(candidate_path: str, snapshot: CandidateSnapshot) -> dict[str, str]:
    section, index, _field_key = repeated_path_parts(candidate_path)
    if not section:
        return {}
    items = snapshot.sections.get(section) or []
    if index < 0 or index >= len(items):
        return {}
    return {"section": section, **items[index]}


def build_open_answer_prompt(
    question: str,
    jd: str,
    snapshot: CandidateSnapshot,
    *,
    company: str = "",
    role: str = "",
    candidate_path: str = "",
) -> str:
    values = snapshot.values
    focus = focus_context(candidate_path, snapshot)
    focus_copy = (
        f"当前字段应围绕第 {repeated_path_parts(candidate_path)[1] + 1} 段{section_label(focus.get('section', ''))}生成："
        f"{focus.get('title') or focus.get('company') or focus.get('school') or ''} {focus.get('summary') or ''}"
        if focus
        else "无特定分段，请综合候选人资料生成。"
    )
    return f"""
你正在帮助候选人填写招聘网站的在线简历表单。请针对字段标题生成一段可直接粘贴到表单里的中文草稿。

字段标题：{question}
字段资料路径：{candidate_path or "未指定"}
分段上下文：{focus_copy}
目标公司：{company or values.get("target_preferences.company") or "未填写"}
目标岗位：{role or values.get("target_preferences.role") or "产品经理"}
岗位 JD：{clean_value(jd)[:1500] or "未提供"}

候选人资料：
姓名：{values.get("basics.name") or "未填写"}
教育：{values.get("education.0.school")} {values.get("education.0.degree")} {values.get("education.0.major")} {values.get("education.0.start_date")}-{values.get("education.0.end_date")}
实习经历：{format_section_for_prompt(snapshot.sections.get("experiences") or []) or "未提取到明确实习经历"}
项目经历：{format_section_for_prompt(snapshot.sections.get("projects") or []) or "未提取到明确项目经历"}
技能：{values.get("skills") or "未提取到明确技能"}

要求：
1. 必须基于候选人已有资料写，不要编造公司、奖项、数据或证书。
2. 如果资料不足，可以写成“我在这段经历中主要负责……”这种稳妥表述，但不要填假事实。
3. 如果字段资料路径指向某一段实习/项目/获奖，必须只围绕该分段生成，不要混用其他分段。
4. 如果字段是实习内容、项目描述、自我评价、申请理由，要输出完整可用草稿。
5. 如果字段是单位介绍，只能写候选人在该单位的实践场景和职责背景；除非候选资料原文提供，否则严禁写“是一家覆盖/拥有/专注于……”这类公司百科式描述。
6. 字数控制在 120-260 字，使用第一人称或中性表述均可，语气正式、具体、适合网申。
7. 只输出正文，不要标题、解释、Markdown 或项目符号。
"""


def is_sensitive_field(field: dict[str, Any]) -> bool:
    return bool(SENSITIVE_FIELD_RE.search(field_text(field)))


def normalize_field(field: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(field.get("id") or ""),
        "tagName": str(field.get("tagName") or "").lower(),
        "inputType": str(field.get("inputType") or "").lower(),
        "label": str(field.get("label") or ""),
        "placeholder": str(field.get("placeholder") or ""),
        "name": str(field.get("name") or ""),
        "ariaLabel": str(field.get("ariaLabel") or ""),
        "nearbyText": str(field.get("nearbyText") or ""),
        "required": bool(field.get("required")),
        "selector": str(field.get("selector") or ""),
        "options": list(field.get("options") or []),
        "currentValue": str(field.get("currentValue") or ""),
    }


def base_mapping(field: dict[str, Any]) -> dict[str, Any]:
    placeholder = str(field.get("placeholder") or "")
    return {
        "field_id": field.get("id", ""),
        "selector": field.get("selector", ""),
        "label": field.get("label") or ("" if is_generic_placeholder(placeholder) else placeholder) or field.get("name") or field.get("nearbyText") or "",
        "field": {
            "tagName": field.get("tagName", ""),
            "inputType": field.get("inputType", ""),
            "label": field.get("label", ""),
            "placeholder": field.get("placeholder", ""),
            "name": field.get("name", ""),
            "ariaLabel": field.get("ariaLabel", ""),
            "nearbyText": field.get("nearbyText", ""),
            "required": bool(field.get("required")),
            "options": list(field.get("options") or [])[:24],
            "currentValue": field.get("currentValue", ""),
        },
    }


def field_text(field: dict[str, Any]) -> str:
    return " ".join(
        str(field.get(key) or "")
        for key in ["label", "placeholder", "name", "ariaLabel", "nearbyText", "inputType", "tagName"]
    ).strip()


def primary_field_text(field: dict[str, Any]) -> str:
    values = [str(field.get(key) or "") for key in ["label", "name", "ariaLabel"]]
    placeholder = str(field.get("placeholder") or "")
    if not is_generic_placeholder(placeholder):
        values.append(placeholder)
    return " ".join(item for item in values if item).strip()


def safe_nearby_text(field: dict[str, Any]) -> str:
    nearby = str(field.get("nearbyText") or "")
    return nearby if len(nearby) <= 48 else ""


def is_custom_picker_field(field: dict[str, Any]) -> bool:
    if str(field.get("inputType") or "").lower() in {"custom_select", "custom_date", "radio_group", "checkbox_group"}:
        return False
    if str(field.get("tagName") or "").lower() != "input":
        return False
    text = field_text(field)
    if str(field.get("inputType") or "").lower() == "search":
        return True
    return bool(re.search(r"(combobox|listbox|select|selector|cascader|picker|dropdown|暂无选项|请选择)", text, re.I))


def unsupported_mapping(field: dict[str, Any], reason: str) -> dict[str, Any]:
    return base_mapping(field) | {
        "candidate_path": "",
        "candidate_label": "",
        "value": "",
        "confidence": 0,
        "status": "unsupported",
        "mapping_type": "safety_guard",
        "reason": reason,
    }


def agent_draft_mapping(field: dict[str, Any], text: str, snapshot: CandidateSnapshot | None = None) -> dict[str, Any]:
    source_path = draft_source_path_for_field(text, snapshot)
    return base_mapping(field) | {
        "candidate_path": source_path or "agent_draft",
        "candidate_label": label_for_path(source_path) if source_path else "桃子 Agent 草稿",
        "value": "",
        "confidence": 0.82,
        "status": "ai_generated",
        "mapping_type": "agent_draft",
        "draft_source_path": source_path,
        "reason": f"识别为核心长文本字段「{clean_value(text)[:28]}」，需要桃子基于简历、档案和 JD 生成草稿。",
    }


def draft_source_path_for_field(text: str, snapshot: CandidateSnapshot | None) -> str:
    if not snapshot:
        return ""
    if re.search(r"(实习|工作|单位介绍|公司介绍|岗位职责|职责描述|工作内容)", text or "", re.I):
        return "experiences.0.summary" if snapshot.values.get("experiences.0.summary") else ""
    if re.search(r"(项目|实践内容|实践经历)", text or "", re.I):
        return "projects.0.summary" if snapshot.values.get("projects.0.summary") else ""
    if re.search(r"(获奖|荣誉|竞赛|奖项)", text or "", re.I):
        return "awards.0.summary" if snapshot.values.get("awards.0.summary") else ""
    return ""


def is_core_draft_field(field: dict[str, Any], text: str) -> bool:
    tag = str(field.get("tagName") or "").lower()
    input_type = str(field.get("inputType") or "").lower()
    if tag not in {"textarea", "div"} and input_type not in {"textarea"}:
        return False
    return bool(CORE_DRAFT_FIELD_RE.search(text) or OPEN_QUESTION_RE.search(text))


def is_question_draft_field(field: dict[str, Any], text: str) -> bool:
    tag = str(field.get("tagName") or "").lower()
    input_type = str(field.get("inputType") or "").lower()
    if tag not in {"textarea", "div"} and input_type not in {"textarea"}:
        return False
    return bool(QUESTION_DRAFT_FIELD_RE.search(text))


def match_score(text: str, alias: str) -> float:
    left = normalize_match_text(text)
    right = normalize_match_text(alias)
    if not right:
        return 0
    if right in left:
        return 1.0
    chars = [char for char in right if char.strip()]
    if not chars:
        return 0
    unique_chars = set(chars)
    overlap = len(unique_chars & set(left)) / len(unique_chars)
    token_bonus = 0.12 if any(token and token in left for token in re.split(r"\s+", right)) else 0
    return min(0.88, overlap + token_bonus)


def normalize_match_text(value: str) -> str:
    return re.sub(r"[\s_\-:：*（）()【】\\[\\]]+", "", str(value or "").lower())


def build_reason(status: str, label: str, has_value: bool) -> str:
    if status == "autofilled":
        return f"命中「{label}」字段，候选人档案已有可填写内容。"
    if status == "needs_confirmation" and has_value:
        return f"可能是「{label}」字段，建议用户确认后填写。"
    if status == "needs_confirmation":
        return f"可能是「{label}」字段，但档案中暂无可靠内容。"
    return "未找到足够可靠的字段映射，保持不填写。"


def first_item(values: Any) -> dict[str, Any]:
    if isinstance(values, list) and values and isinstance(values[0], dict):
        return values[0]
    return {}


def list_items(values: Any) -> list[dict[str, Any]]:
    return [item for item in values or [] if isinstance(item, dict)] if isinstance(values, list) else []


def build_education_values(item: dict[str, Any], resume_text: str) -> dict[str, str]:
    summary = str(item.get("summary") or "")
    return {
        "title": str(item.get("title") or ""),
        "summary": summary,
        "school": extract_school(summary, resume_text),
        "degree": extract_degree(summary, resume_text),
        "degree_type": extract_degree_type(summary or resume_text),
        "major": extract_major(summary, resume_text),
        "start_date": extract_date(summary, "start"),
        "end_date": extract_date(summary, "end"),
    }


def build_experience_values(item: dict[str, Any]) -> dict[str, str]:
    title = str(item.get("title") or "")
    summary = str(item.get("summary") or "")
    return {
        "title": title,
        "summary": summary,
        "company": extract_org(title, summary),
        "role": extract_role(title, summary),
        "location": extract_location(summary),
        "start_date": extract_date(summary, "start"),
        "end_date": extract_date(summary, "end"),
    }


def build_project_values(item: dict[str, Any]) -> dict[str, str]:
    title = str(item.get("title") or "")
    summary = str(item.get("summary") or "")
    return {
        "title": title,
        "summary": summary,
    }


def extract_phone(text: str) -> str:
    match = re.search(r"(?<!\d)(1[3-9]\d[\s-]?\d{4}[\s-]?\d{4})(?!\d)", text or "")
    return match.group(1).replace(" ", "").replace("-", "") if match else ""


def extract_email(text: str) -> str:
    match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text or "", re.I)
    return match.group(0) if match else ""


def extract_school(summary: str, text: str) -> str:
    match = re.search(r"([\u4e00-\u9fa5A-Za-z]{2,24}(?:大学|学院|学校))", summary or text or "")
    return match.group(1) if match else ""


def extract_degree(summary: str, text: str) -> str:
    match = re.search(r"(博士|硕士|研究生|本科|大专|学士)", summary or text or "")
    return match.group(1) if match else ""


def extract_major(summary: str, text: str) -> str:
    match = re.search(r"(?:专业|主修)[:：\s]*([\u4e00-\u9fa5A-Za-z]{2,28})", summary or text or "")
    return match.group(1) if match else ""


def extract_date(summary: str, mode: str) -> str:
    if mode == "end" and re.search(r"(至今|现在|目前)", summary or ""):
        return "至今"
    dates = re.findall(r"(20\d{2}(?:[./-]\d{1,2})?)", summary or "")
    if not dates:
        return ""
    return dates[0] if mode == "start" else dates[-1]


def extract_org(title: str, summary: str) -> str:
    title_value = clean_value(title)
    for separator in [" - ", "｜", "|", "丨", "—", "-"]:
        if separator in title_value:
            candidate = title_value.split(separator, 1)[0]
            if looks_like_org(candidate):
                return clean_org(candidate)

    role_match = ROLE_TOKEN_RE.search(title_value)
    if role_match:
        candidate = title_value[: role_match.start()]
        if looks_like_org(candidate):
            return clean_org(candidate)

    title_candidate = re.sub(r"20\d{2}(?:[./-]\d{1,2})?(?:\s*[-至到]\s*(?:20\d{2}(?:[./-]\d{1,2})?|至今))?", "", title_value)
    title_candidate = ROLE_TOKEN_RE.sub("", title_candidate)
    title_candidate = re.sub(r"(北京|上海|广州|深圳|杭州|南京|成都|武汉|西安|苏州)$", "", title_candidate).strip(" -|｜丨—")
    if looks_like_org(title_candidate):
        return clean_org(title_candidate)

    text = f"{title} {summary}"
    explicit = re.search(r"(?:在|于|加入|任职于|所在单位为)([\u4e00-\u9fa5A-Za-z0-9·&（）()]{2,24})(?:担任|负责|实习|工作|，|。|；|\s)", text or "")
    if explicit and looks_like_org(explicit.group(1)):
        return clean_org(explicit.group(1))

    suffix = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·&（）()]{2,24}(?:公司|集团|科技|网络|银行|研究院|实验室|中心))", text or "")
    return clean_org(suffix.group(1)) if suffix and looks_like_org(suffix.group(1)) else ""


def clean_org(value: str) -> str:
    return clean_value(re.sub(r"^(在|于|加入|任职于)", "", str(value or "")).strip(" -|｜丨—"))


def looks_like_org(value: str) -> bool:
    clean = clean_org(value)
    if not 2 <= len(clean) <= 24:
        return False
    if ORG_STOPWORD_RE.search(clean):
        return False
    if re.search(r"[，。；:：、]", clean):
        return False
    return True


def extract_role(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    match = ROLE_TOKEN_RE.search(text or "")
    return clean_value(match.group(1)) if match else ""


def extract_location(summary: str) -> str:
    match = re.search(r"(?:地点|城市|工作地)[:：\s]*([\u4e00-\u9fa5A-Za-z]{2,16})", summary or "")
    return clean_value(match.group(1)) if match else ""


def extract_current_residence(text: str) -> str:
    match = re.search(r"(?:现居住地|现居地|当前城市|所在地|地址)[:：\s]*([\u4e00-\u9fa5A-Za-z]{2,16})", text or "")
    if match:
        return clean_value(match.group(1))
    match = re.search(r"(?:至今|现在|目前)[^\n。；;]{0,16}(北京|上海|广州|深圳|杭州|南京|成都|武汉|西安|苏州|天津|重庆)", text or "")
    return match.group(1) if match else ""


def extract_political_status(text: str) -> str:
    match = re.search(r"(中共党员|预备党员|共青团员|党员|团员|群众)", text or "")
    return match.group(1) if match else ""


def extract_overseas_experience(text: str) -> str:
    if re.search(r"(海外留学|留学经历|交换生|海外交换|境外学习)", text or ""):
        return "有"
    if re.search(r"(无海外|无留学|没有海外|没有留学)", text or ""):
        return "无"
    return ""


def extract_application_type(text: str, graduation_date: str) -> str:
    if re.search(r"应届", text or ""):
        return "应届"
    if re.search(r"往届|社招", text or ""):
        return "往届"
    match = re.search(r"(20\d{2})", graduation_date or "")
    if not match:
        return ""
    grad_year = int(match.group(1))
    current_year = date.today().year
    return "应届" if current_year <= grad_year <= current_year + 2 else "往届"


def extract_professional_title(text: str) -> str:
    match = re.search(r"(高级工程师|工程师|助理工程师|经济师|会计师|无职称)", text or "")
    if match:
        return "无" if match.group(1) == "无职称" else match.group(1)
    return ""


def extract_english_level(text: str) -> str:
    patterns = [
        r"(CET[-\s]?(?:4|6)|英语[四六]级|大学英语[四六]级|TEM[-\s]?(?:4|8)|专业英语[四八]级)",
        r"(雅思\s*\d(?:\.\d)?|IELTS\s*\d(?:\.\d)?|托福\s*\d{2,3}|TOEFL\s*\d{2,3})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if match:
            return clean_value(match.group(1).replace("英语四级", "CET-4").replace("英语六级", "CET-6"))
    return ""


def extract_degree_type(text: str) -> str:
    if re.search(r"(专硕|专业型硕士|专业学位硕士|专业学位)", text or ""):
        return "专业型硕士"
    if re.search(r"(学硕|学术型硕士|学术学位硕士|学术学位)", text or ""):
        return "学术型硕士"
    return ""


def build_career_objective(profile: UserProfile, candidate: CandidateProfile) -> str:
    target = candidate.target_preferences or {}
    role = str(target.get("role") or profile.target_role or "")
    company = str(target.get("company") or profile.target_company or "")
    if role and company:
        return f"希望应聘{company}{role}岗位，持续发展产品规划、需求分析、项目推进和数据复盘能力。"
    if role:
        return f"希望应聘{role}相关岗位，持续发展产品规划、需求分析、项目推进和数据复盘能力。"
    return ""


def extract_awards(text: str) -> str:
    match = re.search(r"(?:获奖|奖项|荣誉|竞赛经历)[:：]?\s*([\s\S]{0,240})", text or "")
    return clean_value(match.group(1)) if match else ""


def extract_award_items(text: str) -> list[dict[str, str]]:
    awards_text = extract_awards(text)
    if not awards_text:
        return []
    chunks = [
        clean_value(chunk.strip(" -•、,，;；"))
        for chunk in re.split(r"\n|[;；]", awards_text)
        if clean_value(chunk.strip(" -•、,，;；"))
    ]
    if len(chunks) <= 1 and "、" in awards_text:
        chunks = [clean_value(chunk) for chunk in awards_text.split("、") if clean_value(chunk)]
    items = []
    for chunk in chunks[:4]:
        title = re.sub(r"(?:时间|日期|获奖时间)[:：]?\s*20\d{2}(?:[./-]\d{1,2})?", "", chunk)
        title = re.sub(r"(?:说明|描述)[:：].*", "", title)
        items.append(
            {
                "title": clean_value(title)[:80],
                "summary": chunk[:240],
            }
        )
    return items


def clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_generic_placeholder(value: str) -> bool:
    text = clean_value(value)
    return not text or text in {"请输入", "请选择", "请填写", "请输入内容", "请输入文本"}
