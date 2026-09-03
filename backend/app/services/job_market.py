from __future__ import annotations

import csv
import hashlib
import os
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.app.models import UserProfile


JOB_FIELDS = [
    "行业",
    "批次",
    "不限专业",
    "公司名称",
    "学历",
    "岗位更新日期",
    "官方公告",
    "岗位",
    "网申入口",
    "含免笔试",
    "截止时间",
    "企业类型",
    "招聘对象",
    "备注",
    "工作城市",
]
DEFAULT_JOB_CSV = Path(__file__).resolve().parents[1] / "datasets" / "autumn_recruitment.csv"


def search_job_library(
    *,
    query: str = "",
    industry: str = "",
    batch: str = "",
    city: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    rows = load_job_rows()
    filtered = [
        row
        for row in rows
        if matches_query(row, query)
        and matches_value(row, "industry", industry)
        and matches_value(row, "batch", batch)
        and matches_value(row, "cities", city)
    ]
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))
    return {
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "items": filtered[offset : offset + limit],
        "facets": build_facets(rows),
    }


def recommend_jobs_for_profile(profile: UserProfile, *, limit: int = 6, query: str = "") -> dict[str, Any]:
    rows = load_job_rows()
    scored = []
    for row in rows:
        score, reasons = score_job(row, profile)
        preference_score, preference_reasons = score_query_preferences(row, query)
        if score + preference_score <= 0:
            continue
        total_score = max(1, min(99, score + preference_score))
        scored.append(
            (
                {**row, "match_score": total_score, "match_reasons": unique([*preference_reasons, *reasons])[:4]},
                total_score,
                preference_score,
                score,
            )
        )
    scored.sort(key=lambda item: (item[1], item[2], item[3], freshness_rank(item[0])), reverse=True)
    items = [item for item, *_ in scored[: max(1, min(limit, 20))]]
    return {
        "items": items,
        "total": len(scored),
        "profile_target": {
            "role": profile.target_role or "产品经理",
            "company": profile.target_company or "",
            "city": profile.target_city or "",
            "stage": profile.stage or "投递期",
        },
        "source": "autumn_recruitment_csv",
    }


@lru_cache(maxsize=1)
def load_job_rows() -> list[dict[str, Any]]:
    path = Path(os.environ.get("PEACH_JOB_MARKET_CSV") or DEFAULT_JOB_CSV)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for index, raw in enumerate(reader):
            row = normalize_job_row(raw, index)
            if row["company"] or row["position"]:
                rows.append(row)
    return rows


def normalize_job_row(raw: dict[str, str], index: int) -> dict[str, Any]:
    company = clean(raw.get("公司名称"))
    position = clean(raw.get("岗位"))
    url = clean(raw.get("网申入口"))
    announcement_url = clean(raw.get("官方公告"))
    batch = clean(raw.get("批次"))
    deadline = clean(raw.get("截止时间"))
    digest = hashlib.sha1(f"{index}|{company}|{position}|{url}".encode("utf-8")).hexdigest()[:12]
    return {
        "id": f"job-{digest}",
        "industry": clean(raw.get("行业")),
        "batch": batch,
        "major_friendly": clean(raw.get("不限专业")) == "1",
        "company": company,
        "education": clean(raw.get("学历")),
        "updated_at": clean(raw.get("岗位更新日期")),
        "announcement_url": announcement_url,
        "position": position,
        "application_url": url,
        "written_test_free": clean(raw.get("含免笔试")) == "1",
        "deadline": deadline,
        "deadline_status": deadline_status(deadline),
        "company_type": clean(raw.get("企业类型")),
        "target_graduates": clean(raw.get("招聘对象")),
        "notes": clean(raw.get("备注")),
        "cities": clean(raw.get("工作城市")),
    }


def score_job(row: dict[str, Any], profile: UserProfile) -> tuple[int, list[str]]:
    role = clean(profile.target_role) or "产品经理"
    company = clean(profile.target_company)
    city = clean(profile.target_city)
    resume = clean(profile.resume_text)
    haystack = " ".join(str(row.get(key) or "") for key in ["company", "position", "industry", "company_type", "notes", "cities"])
    score = 0
    reasons: list[str] = []

    for token in role_tokens(role):
        if token and token in haystack:
            score += 18
            reasons.append(f"岗位信息包含「{token}」")
            break
    if "产品" in role and re.search(r"(产品|PM|用户|策略|增长|运营)", haystack, re.I):
        score += 22
        reasons.append("岗位方向接近产品经理")
    if re.search(r"(AI|AIGC|大模型|算法|数据|智能|Agent)", role + resume, re.I) and re.search(r"(AI|AIGC|大模型|算法|数据|智能|Agent)", haystack, re.I):
        score += 14
        reasons.append("与 AI/数据经历有交集")
    if company and company in row.get("company", ""):
        score += 20
        reasons.append("匹配目标公司")
    if city and city in row.get("cities", ""):
        score += 10
        reasons.append(f"城市包含{city}")

    grad_year = infer_grad_year(profile)
    if grad_year and str(grad_year) in row.get("target_graduates", ""):
        score += 12
        reasons.append(f"面向 {grad_year} 届")
    if row.get("major_friendly"):
        score += 7
        reasons.append("不限专业")
    if row.get("written_test_free"):
        score += 4
        reasons.append("标注免笔试")
    if row.get("batch") in {"27届秋招", "秋招提前批", "暑期实习", "日常实习"}:
        score += 9
        reasons.append(row.get("batch"))

    status = row.get("deadline_status")
    if status == "expired":
        score -= 18
    elif status == "open":
        score += 6

    if not reasons and score <= 0:
        return 0, []
    return max(1, min(99, score)), unique(reasons)[:4]


def score_query_preferences(row: dict[str, Any], query: str) -> tuple[int, list[str]]:
    text = clean(query)
    if not text:
        return 0, []
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ["company", "position", "industry", "company_type", "notes", "cities", "batch", "target_graduates"]
    )
    score = 0
    reasons: list[str] = []

    if any(word in text for word in ["大厂", "头部", "一线", "互联网大厂"]):
        if re.search(r"(腾讯|阿里|字节|百度|美团|京东|网易|快手|小米|华为|蚂蚁|滴滴|拼多多|B站|哔哩|携程|知乎|贝壳|抖音)", haystack, re.I):
            score += 24
            reasons.append("符合大厂/头部平台偏好")
    if any(word in text for word in ["中台", "平台", "基础能力", "基础平台"]):
        if re.search(r"(中台|平台|策略|数据产品|商业化|基础架构|AI Infra|工具|效率)", haystack, re.I):
            score += 18
            reasons.append("更接近中台/平台方向")
    if any(word in text for word in ["偏算法", "算法", "技术", "AI", "大模型", "数据", "推荐", "搜索"]):
        if re.search(r"(算法|AI|AIGC|大模型|机器学习|数据|推荐|搜索|智能|Agent|工程)", haystack, re.I):
            score += 20
            reasons.append("与算法/AI/数据方向相关")
    if any(word in text for word in ["偏业务", "业务", "增长", "商业化", "运营", "用户"]):
        if re.search(r"(业务|增长|商业化|运营|用户|市场|销售|客户|供应链|行业)", haystack, re.I):
            score += 18
            reasons.append("贴近业务/增长场景")
    if "免笔试" in text and row.get("written_test_free"):
        score += 12
        reasons.append("标注免笔试")
    if "不限专业" in text and row.get("major_friendly"):
        score += 10
        reasons.append("不限专业")

    for city in ["北京", "上海", "深圳", "广州", "杭州", "南京", "成都", "武汉", "西安", "苏州"]:
        if city in text and city in str(row.get("cities") or ""):
            score += 10
            reasons.append(f"城市包含{city}")
            break

    for batch in ["27届秋招", "秋招提前批", "暑期实习", "日常实习", "春招"]:
        if batch in text and batch in str(row.get("batch") or ""):
            score += 10
            reasons.append(batch)
            break

    for token in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,20}", text):
        if token in haystack and token not in {"岗位推荐", "推荐岗位", "帮我", "想要"}:
            score += 8
            reasons.append(f"命中偏好「{token}」")
            break

    return score, unique(reasons)[:3]


def matches_query(row: dict[str, Any], query: str) -> bool:
    text = clean(query).lower()
    if not text:
        return True
    haystack = " ".join(str(value or "") for value in row.values()).lower()
    return all(token in haystack for token in re.split(r"\s+", text) if token)


def matches_value(row: dict[str, Any], key: str, value: str) -> bool:
    needle = clean(value)
    return not needle or needle in str(row.get(key) or "")


def build_facets(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "industries": top_values(rows, "industry"),
        "batches": top_values(rows, "batch"),
        "company_types": top_values(rows, "company_type"),
    }


def top_values(rows: list[dict[str, Any]], key: str, limit: int = 16) -> list[str]:
    counts: dict[str, int] = {}
    for row in rows:
        for value in split_values(str(row.get(key) or "")):
            counts[value] = counts.get(value, 0) + 1
    return [value for value, _count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]


def split_values(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,，、/]", value or "") if item.strip()]


def role_tokens(role: str) -> list[str]:
    tokens = split_values(role)
    tokens.extend(re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}", role or ""))
    if "产品" in role:
        tokens.extend(["产品经理", "产品", "PM", "策略", "增长"])
    return unique(tokens)


def infer_grad_year(profile: UserProfile) -> int | None:
    text = " ".join([profile.resume_text or "", profile.stage or ""])
    match = re.search(r"(\d{2})届", text)
    if match:
        return 2000 + int(match.group(1))
    match = re.search(r"20(2[5-9])", text)
    return int(f"20{match.group(1)}") if match else None


def deadline_status(value: str) -> str:
    text = clean(value)
    if not text or any(word in text for word in ["招满", "尽快", "长期", "滚动"]):
        return "open"
    try:
        parsed = datetime.strptime(text.replace("/", "-"), "%Y-%m-%d").date()
    except ValueError:
        return "unknown"
    return "expired" if parsed < date.today() else "open"


def freshness_rank(row: dict[str, Any]) -> int:
    updated = str(row.get("updated_at") or "").replace("/", "-")
    try:
        return int(datetime.strptime(updated, "%Y-%m-%d").strftime("%Y%m%d"))
    except ValueError:
        return 0


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
