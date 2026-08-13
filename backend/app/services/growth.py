from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    AbilityScoreHistory,
    ActionState,
    AgentMemory,
    GrowthInsight,
    GrowthIssue,
    InterviewSession,
    UserAbilityScore,
    UserProfile,
)
from backend.app.services.memory import upsert_memory
from backend.app.services.recommendations import get_home_recommendations


ABILITY_DIMENSIONS = [
    ("product_thinking", "产品思维", 80),
    ("user_insight", "用户洞察", 80),
    ("requirement_analysis", "需求分析", 80),
    ("data_analysis", "数据分析", 82),
    ("project_deep_dive", "项目深挖", 82),
    ("project_management", "项目推进", 78),
    ("business_judgment", "商业判断", 76),
    ("structured_expression", "结构化表达", 75),
]

ABILITY_LABELS = {key: label for key, label, _ in ABILITY_DIMENSIONS}
ABILITY_TARGETS = {key: target for key, _, target in ABILITY_DIMENSIONS}

ISSUE_TAXONOMY = {
    "project_decision_reasoning": {
        "title": "项目决策依据不足",
        "ability": "project_deep_dive",
        "keywords": ["决策", "为什么", "优先", "取舍", "方案", "依据"],
        "description": "项目深挖时，需要更清楚说明为什么这么做、如何取舍和如何判断优先级。",
    },
    "data_attribution": {
        "title": "数据结果归因不完整",
        "ability": "data_analysis",
        "keywords": ["数据", "指标", "归因", "%", "提升", "增长", "转化", "留存"],
        "description": "能说出结果，但还需要解释指标变化和个人动作之间的关系。",
    },
    "business_value": {
        "title": "业务价值表达不够具体",
        "ability": "business_judgment",
        "keywords": ["业务", "价值", "收入", "成本", "效率", "商业化", "ROI"],
        "description": "回答需要把功能动作进一步落到用户价值、业务收益或组织效率。",
    },
    "structured_expression": {
        "title": "回答结构还不够稳定",
        "ability": "structured_expression",
        "keywords": ["结构", "逻辑", "首先", "其次", "最后", "总结"],
        "description": "回答需要保持结论先行，并用清晰层次承接事实和结果。",
    },
}


@dataclass
class GrowthUpdate:
    abilities: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    insights: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    memory_updates: list[dict[str, Any]]


async def apply_interview_growth_update(
    session: AsyncSession,
    profile: UserProfile,
    interview: InterviewSession,
) -> GrowthUpdate:
    report = interview.report or {}
    if report.get("growth_loop_applied"):
        return GrowthUpdate(
            abilities=report.get("ability_updates", []),
            issues=report.get("growth_findings", []),
            insights=report.get("growth_insights", []),
            actions=report.get("next_actions", []),
            memory_updates=report.get("memory_updates", []),
        )

    ability_updates = extract_ability_evidence(interview)
    issues = detect_growth_issues(interview, report)
    memory_updates: list[dict[str, Any]] = []

    for ability in ability_updates:
        history = AbilityScoreHistory(
            user_id=profile.id,
            ability_dimension=ability["dimension"],
            score=ability["score"],
            source_type="mock_interview",
            source_id=interview.id,
            evidence=ability["evidence"],
        )
        session.add(history)
        await update_user_ability_score(session, profile.id, ability["dimension"], ability["score"])

    persisted_issues: list[GrowthIssue] = []
    for issue_data in issues:
        issue = await upsert_growth_issue(session, profile.id, issue_data, interview.id)
        persisted_issues.append(issue)
    if persisted_issues:
        await session.flush()

    for issue in persisted_issues:
        memory = await upsert_memory(
            session,
            profile.id,
            {
                "kind": "interview_pattern",
                "content": f"{issue.title}：{issue.description}",
                "source": "growth_issue",
                "confidence": confidence_from_count(issue.occurrence_count),
                "tags": ["growth_issue", issue.issue_key, issue.ability_dimension],
                "memory_metadata": {
                    "memory_key": f"interview_weakness.{issue.issue_key}",
                    "status": "improving" if issue.status == "improving" else "active",
                    "stability": "dynamic",
                    "evidence_count": issue.occurrence_count,
                    "source_interview_id": interview.id,
                },
            },
        )
        memory_updates.append({"id": memory.id, "content": memory.content, "status": memory.memory_metadata.get("status")})

    insights = await create_growth_insights(session, profile, interview, persisted_issues)
    actions = await create_next_actions(session, profile, persisted_issues)
    await enrich_report_with_growth(report, ability_updates, persisted_issues, insights, actions, memory_updates)
    interview.report = report

    return GrowthUpdate(
        abilities=ability_updates,
        issues=[serialize_issue(issue) for issue in persisted_issues],
        insights=[serialize_insight(item) for item in insights],
        actions=[serialize_action(item) for item in actions],
        memory_updates=memory_updates,
    )


async def update_user_ability_score(session: AsyncSession, user_id: str, dimension: str, score: int) -> UserAbilityScore:
    existing = (
        await session.execute(
            select(UserAbilityScore)
            .where(UserAbilityScore.user_id == user_id, UserAbilityScore.ability_dimension == dimension)
            .limit(1)
        )
    ).scalar_one_or_none()
    if not existing:
        existing = UserAbilityScore(
            user_id=user_id,
            ability_dimension=dimension,
            current_score=score,
            target_score=ABILITY_TARGETS.get(dimension, 80),
            confidence_level="low",
            evidence_count=1,
        )
        session.add(existing)
        return existing

    evidence_count = (existing.evidence_count or 0) + 1
    smoothed = round((existing.current_score or score) * 0.65 + score * 0.35)
    existing.current_score = max(0, min(100, smoothed))
    existing.evidence_count = evidence_count
    existing.confidence_level = confidence_level(evidence_count)
    return existing


async def upsert_growth_issue(session: AsyncSession, user_id: str, issue_data: dict[str, Any], interview_id: str) -> GrowthIssue:
    issue = (
        await session.execute(
            select(GrowthIssue)
            .where(GrowthIssue.user_id == user_id, GrowthIssue.issue_key == issue_data["issue_key"])
            .limit(1)
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not issue:
        issue = GrowthIssue(
            user_id=user_id,
            issue_key=issue_data["issue_key"],
            title=issue_data["title"],
            description=issue_data["description"],
            ability_dimension=issue_data["ability_dimension"],
            status="new",
            occurrence_count=1,
            evidence_ids=[interview_id],
            last_detected_at=now,
        )
        session.add(issue)
        return issue

    issue.occurrence_count = (issue.occurrence_count or 0) + 1
    issue.description = issue_data["description"]
    issue.ability_dimension = issue_data["ability_dimension"]
    issue.status = issue_status_from_count(issue.occurrence_count)
    issue.evidence_ids = unique_ids([*(issue.evidence_ids or []), interview_id])
    issue.last_detected_at = now
    return issue


async def create_growth_insights(
    session: AsyncSession,
    profile: UserProfile,
    interview: InterviewSession,
    issues: list[GrowthIssue],
) -> list[GrowthInsight]:
    if not issues:
        content = f"这场 {interview.role or profile.target_role} 面试没有暴露新的持续性问题，后续可以用完整 Mock 验证稳定性。"
        insight = GrowthInsight(user_id=profile.id, insight_type="improvement", content=content, evidence_ids=[interview.id], confidence=65)
        session.add(insight)
        return [insight]

    primary = issues[0]
    if primary.occurrence_count <= 1:
        content = f"桃子注意到一次「{primary.title}」，后续会在模拟面试中多追问相关证据。"
        insight_type = "new_issue"
    elif primary.occurrence_count == 2:
        content = f"最近「{primary.title}」出现了不止一次，建议优先做专项训练。"
        insight_type = "bottleneck"
    else:
        content = f"「{primary.title}」可能已经成为持续性瓶颈，下一阶段先围绕{ABILITY_LABELS.get(primary.ability_dimension, '相关能力')}练透。"
        insight_type = "bottleneck"
    insight = GrowthInsight(user_id=profile.id, insight_type=insight_type, content=content, evidence_ids=[interview.id], confidence=confidence_from_count(primary.occurrence_count))
    session.add(insight)
    return [insight]


async def create_next_actions(session: AsyncSession, profile: UserProfile, issues: list[GrowthIssue]) -> list[ActionState]:
    if not issues:
        return []

    primary = sorted(issues, key=lambda item: item.occurrence_count or 0, reverse=True)[0]
    existing = (
        await session.execute(
            select(ActionState)
            .where(
                ActionState.user_id == profile.id,
                ActionState.status == "pending",
                ActionState.target_issue_id == primary.id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        return [existing]

    action = ActionState(
        user_id=profile.id,
        action_type="targeted_interview_training",
        title=f"{ABILITY_LABELS.get(primary.ability_dimension, '面试')}专项训练",
        description=f"围绕「{primary.title}」继续练 3-5 题，重点补齐决策依据、数据结果和业务价值。",
        target_issue_id=primary.id,
        target_ability=primary.ability_dimension,
        priority=1,
    )
    session.add(action)
    await session.flush()
    return [action]


async def enrich_report_with_growth(
    report: dict[str, Any],
    ability_updates: list[dict[str, Any]],
    issues: list[GrowthIssue],
    insights: list[GrowthInsight],
    actions: list[ActionState],
    memory_updates: list[dict[str, Any]],
) -> None:
    report["growth_loop_applied"] = True
    report["growth_findings"] = [
        {
            "title": issue.title,
            "description": issue.description,
            "status": issue.status,
            "occurrence_count": issue.occurrence_count,
            "ability_dimension": issue.ability_dimension,
        }
        for issue in issues[:3]
    ]
    report["ability_updates"] = ability_updates[:8]
    report["memory_updates"] = memory_updates[:5]
    report["next_actions"] = [serialize_action(action) for action in actions[:3]]
    report["growth_insights"] = [serialize_insight(insight) for insight in insights[:3]]


async def build_home_context(session: AsyncSession, profile: UserProfile) -> dict[str, Any]:
    memories = (
        await session.execute(
            select(AgentMemory)
            .where(AgentMemory.user_id == profile.id)
            .order_by(desc(AgentMemory.updated_at))
            .limit(40)
        )
    ).scalars().all()
    issues = (
        await session.execute(
            select(GrowthIssue)
            .where(GrowthIssue.user_id == profile.id)
            .order_by(desc(GrowthIssue.updated_at))
            .limit(8)
        )
    ).scalars().all()
    insights = (
        await session.execute(
            select(GrowthInsight)
            .where(GrowthInsight.user_id == profile.id)
            .order_by(desc(GrowthInsight.created_at))
            .limit(4)
        )
    ).scalars().all()
    actions = await pending_actions(session, profile.id, limit=4)
    view = build_peach_view_of_user(profile, list(memories), list(issues), list(insights))
    recommendations = await get_home_recommendations(session, profile.id)
    return {
        "peach_view_of_user": view,
        "personalized_prompts": [item["text"] for item in recommendations],
        "personalized_recommendations": recommendations,
        "pending_actions": [serialize_action(action) for action in actions],
    }


async def build_growth_center(session: AsyncSession, profile: UserProfile) -> dict[str, Any]:
    scores = (
        await session.execute(
            select(UserAbilityScore)
            .where(UserAbilityScore.user_id == profile.id)
            .order_by(UserAbilityScore.ability_dimension)
        )
    ).scalars().all()
    histories = (
        await session.execute(
            select(AbilityScoreHistory)
            .where(AbilityScoreHistory.user_id == profile.id)
            .order_by(AbilityScoreHistory.created_at)
            .limit(80)
        )
    ).scalars().all()
    issues = (
        await session.execute(
            select(GrowthIssue)
            .where(GrowthIssue.user_id == profile.id)
            .order_by(desc(GrowthIssue.updated_at))
            .limit(20)
        )
    ).scalars().all()
    insights = (
        await session.execute(
            select(GrowthInsight)
            .where(GrowthInsight.user_id == profile.id)
            .order_by(desc(GrowthInsight.created_at))
            .limit(5)
        )
    ).scalars().all()
    actions = await pending_actions(session, profile.id, limit=1)
    abilities = serialize_abilities(list(scores))
    readiness = readiness_score(abilities)
    return {
        "target": {
            "role": profile.target_role or "产品经理",
            "company": profile.target_company,
            "jd_status": "已基于当前档案评估" if profile.resume_text else "当前按照产品经理通用能力模型评估",
        },
        "readiness_score": readiness,
        "abilities": abilities,
        "trend": build_readiness_trend(list(histories)),
        "issues": group_issues(list(issues)),
        "insights": [serialize_insight(item) for item in insights],
        "recommendation": serialize_action(actions[0]) if actions else default_growth_action(profile),
        "stats": build_growth_stats(list(histories), list(issues)),
    }


async def pending_actions(session: AsyncSession, user_id: str, limit: int) -> list[ActionState]:
    return list((
        await session.execute(
            select(ActionState)
            .where(ActionState.user_id == user_id, ActionState.status == "pending")
            .order_by(ActionState.priority, desc(ActionState.updated_at))
            .limit(limit)
        )
    ).scalars().all())


def extract_ability_evidence(interview: InterviewSession) -> list[dict[str, Any]]:
    report = interview.report or {}
    dimensions = normalize_report_dimensions(report)
    transcript = interview.transcript or []
    candidate_text = "\n".join(str(item.get("content") or "") for item in transcript if item.get("role") == "candidate")
    answers = [str(item.get("content") or "") for item in transcript if item.get("role") == "candidate"]
    evidence = {
        "source_type": "mock_interview",
        "source_id": interview.id,
        "excerpt": candidate_text[:420],
        "answer_count": len(answers),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return [
        {"dimension": dimension, "score": score, "evidence": {**evidence, "dimension_label": ABILITY_LABELS[dimension]}}
        for dimension, score in dimensions.items()
    ]


def normalize_report_dimensions(report: dict[str, Any]) -> dict[str, int]:
    raw = report.get("dimensions") if isinstance(report, dict) else []
    by_name = {str(item.get("name") or ""): int(item.get("score") or 70) for item in raw if isinstance(item, dict)}
    structured = {
        "structured_expression": by_name.get("语言精简度", by_name.get("语言流畅度", 72)),
        "project_deep_dive": by_name.get("岗位核心能力", 70),
        "data_analysis": min(100, by_name.get("岗位核心能力", 70) + 2),
        "business_judgment": max(50, by_name.get("岗位核心能力", 70) - 4),
    }
    return {key: max(0, min(100, value)) for key, value in structured.items()}


def detect_growth_issues(interview: InterviewSession, report: dict[str, Any]) -> list[dict[str, Any]]:
    text = "\n".join([
        str(report.get("summary") or ""),
        " ".join(str(item) for item in report.get("key_improvements") or []),
        " ".join(str(item.get("candidate_transcript") or "") for item in report.get("question_review") or [] if isinstance(item, dict)),
        " ".join(str(item.get("content") or "") for item in interview.transcript or [] if item.get("role") == "candidate"),
    ])
    issues: list[dict[str, Any]] = []
    for issue_key, spec in ISSUE_TAXONOMY.items():
        matched = any(keyword in text for keyword in spec["keywords"])
        if not matched and issue_key == "project_decision_reasoning":
            matched = True
        if matched:
            issues.append({
                "issue_key": issue_key,
                "title": spec["title"],
                "description": spec["description"],
                "ability_dimension": spec["ability"],
            })
    return issues[:2]


def build_peach_view_of_user(
    profile: UserProfile,
    memories: list[AgentMemory],
    issues: list[GrowthIssue],
    insights: list[GrowthInsight],
) -> list[dict[str, str]]:
    active_memories = [item for item in memories if memory_status(item) not in {"archived", "superseded", "resolved"}]
    items = [
        {"label": "目标", "value": f"{profile.target_company + ' · ' if profile.target_company else ''}{profile.target_role or '产品经理'}"},
    ]
    experience = first_memory(active_memories, {"project_signal", "resume_signal", "skill_signal", "profile_fact"})
    if experience:
        items.append({"label": "核心经历", "value": short_text(experience.content, 42)})
    highlight = first_memory(active_memories, {"skill_signal", "resume_signal"})
    if highlight and highlight.id != getattr(experience, "id", ""):
        items.append({"label": "经历亮点", "value": short_text(highlight.content, 42)})
    active_issue = next((item for item in issues if item.status in {"new", "improving"}), None)
    if active_issue:
        items.append({"label": "最近需要提升", "value": active_issue.title})
    insight = next(iter(insights), None)
    if insight:
        items.append({"label": "最近的变化", "value": short_text(insight.content, 44)})
    preference = first_memory(active_memories, {"preference"})
    if preference:
        items.append({"label": "表达偏好", "value": short_text(preference.content, 42)})
    return items[:6]


def build_personalized_prompts(
    profile: UserProfile,
    issues: list[GrowthIssue],
    insights: list[GrowthInsight],
    actions: list[ActionState],
) -> list[str]:
    prompts: list[str] = []
    if actions:
        prompts.append(f"继续上次的{actions[0].title}")
    improving = next((item for item in issues if item.status == "improving"), None)
    if improving:
        prompts.append(f"上次{ABILITY_LABELS.get(improving.ability_dimension, '面试')}还有几题没答透，我们继续练练？")
    new_issue = next((item for item in issues if item.status == "new"), None)
    if new_issue:
        prompts.append(f"要不要把上次暴露的{new_issue.title}练一下？")
    if profile.target_role:
        prompts.append(f"按{profile.target_role}再来一场针对性 Mock")
    if insights:
        prompts.append("把桃子最近发现的问题变成训练计划")
    return unique_strings(prompts)[:4]


def serialize_abilities(scores: list[UserAbilityScore]) -> list[dict[str, Any]]:
    by_dimension = {item.ability_dimension: item for item in scores}
    values: list[dict[str, Any]] = []
    for key, label, target in ABILITY_DIMENSIONS:
        score = by_dimension.get(key)
        current = score.current_score if score else None
        evidence_count = score.evidence_count if score else 0
        values.append({
            "dimension": key,
            "label": label,
            "current_score": current,
            "target_score": score.target_score if score else target,
            "gap": None if current is None else max(0, (score.target_score if score else target) - current),
            "status": ability_status(current, score.target_score if score else target, evidence_count),
            "confidence_level": score.confidence_level if score else "待评估",
            "evidence_count": evidence_count,
        })
    return values


def readiness_score(abilities: list[dict[str, Any]]) -> int:
    valid = [item for item in abilities if item["current_score"] is not None and item["evidence_count"] >= 1]
    if not valid:
        return 0
    ratios = [min(1.05, item["current_score"] / max(1, item["target_score"])) for item in valid]
    return max(0, min(100, round(sum(ratios) / len(ratios) * 100)))


def build_readiness_trend(histories: list[AbilityScoreHistory]) -> list[dict[str, Any]]:
    if not histories:
        return []
    buckets: dict[str, list[int]] = {}
    for item in histories:
        label = item.created_at.strftime("%m-%d") if item.created_at else "今日"
        buckets.setdefault(label, []).append(item.score)
    return [{"label": label, "score": round(sum(scores) / len(scores))} for label, scores in buckets.items()]


def group_issues(issues: list[GrowthIssue]) -> dict[str, list[dict[str, Any]]]:
    groups = {"solved": [], "improving": [], "new": []}
    for issue in issues:
        key = issue.status if issue.status in groups else "new"
        groups[key].append(serialize_issue(issue))
    return groups


def build_growth_stats(histories: list[AbilityScoreHistory], issues: list[GrowthIssue]) -> dict[str, int]:
    return {
        "ability_evidence_count": len(histories),
        "tracked_issue_count": len(issues),
        "solved_issue_count": len([item for item in issues if item.status == "solved"]),
    }


def default_growth_action(profile: UserProfile) -> dict[str, Any]:
    return {
        "id": "default-project-deep-dive",
        "title": "项目深挖专项训练",
        "description": f"当前按「{profile.target_role or '产品经理'}」通用能力模型，先练为什么做、怎么决策、结果如何。",
        "target_ability": "project_deep_dive",
        "target_issue_id": "",
        "status": "pending",
        "priority": 2,
    }


def serialize_action(action: ActionState) -> dict[str, Any]:
    return {
        "id": action.id,
        "action_type": action.action_type,
        "title": action.title,
        "description": action.description,
        "target_issue_id": action.target_issue_id,
        "target_ability": action.target_ability,
        "status": action.status,
        "priority": action.priority,
    }


def serialize_issue(issue: GrowthIssue) -> dict[str, Any]:
    return {
        "id": issue.id,
        "issue_key": issue.issue_key,
        "title": issue.title,
        "description": issue.description,
        "ability_dimension": issue.ability_dimension,
        "status": issue.status,
        "occurrence_count": issue.occurrence_count,
        "evidence_ids": issue.evidence_ids or [],
    }


def serialize_insight(insight: GrowthInsight) -> dict[str, Any]:
    return {
        "id": insight.id,
        "insight_type": insight.insight_type,
        "content": insight.content,
        "evidence_ids": insight.evidence_ids or [],
        "confidence": insight.confidence,
    }


def ability_status(current: int | None, target: int, evidence_count: int) -> str:
    if current is None or evidence_count < 1:
        return "pending"
    gap = target - current
    if gap <= 0:
        return "achieved"
    if gap <= 5:
        return "close"
    if gap <= 15:
        return "improve"
    return "priority"


def confidence_level(count: int) -> str:
    if count >= 4:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def confidence_from_count(count: int) -> int:
    if count >= 3:
        return 88
    if count == 2:
        return 78
    return 68


def issue_status_from_count(count: int) -> str:
    if count >= 3:
        return "improving"
    if count == 2:
        return "improving"
    return "new"


def memory_status(memory: AgentMemory) -> str:
    return str((memory.memory_metadata or {}).get("status") or "active")


def first_memory(memories: list[AgentMemory], kinds: set[str]) -> AgentMemory | None:
    return next((item for item in memories if item.kind in kinds and item.content.strip()), None)


def short_text(value: str, limit: int) -> str:
    clean = " ".join(str(value or "").split())
    return clean if len(clean) <= limit else f"{clean[:limit]}..."


def unique_ids(values: list[str]) -> list[str]:
    return unique_strings([value for value in values if value])


def unique_strings(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.append(clean)
    return seen
