from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    ActionState,
    AgentMemory,
    GrowthInsight,
    GrowthIssue,
    HomeRecommendation,
    KnowledgeResource,
    UserProfile,
)


TRIGGER_PROBABILITIES = {
    "memory": 0.35,
    "profile": 0.45,
    "resume": 0.45,
    "knowledge": 0.30,
    "practice": 0.40,
    "review": 0.50,
    "action": 0.40,
    "interview_finish": 1.0,
    "default": 0.35,
}


@dataclass(frozen=True)
class RecommendationCandidate:
    text: str
    reason: str
    source_type: str
    source_id: str
    action_type: str = "chat"
    priority: int = 3


async def get_home_recommendations(session: AsyncSession, user_id: str, limit: int = 4) -> list[dict]:
    items = (
        await session.execute(
            select(HomeRecommendation)
            .where(HomeRecommendation.user_id == user_id, HomeRecommendation.status == "active")
            .order_by(HomeRecommendation.priority, desc(HomeRecommendation.created_at))
            .limit(limit)
        )
    ).scalars().all()
    return [serialize_recommendation(item) for item in items]


async def refresh_home_recommendations(
    session: AsyncSession,
    profile: UserProfile,
    *,
    trigger_reason: str = "default",
    source_type: str = "",
    source_id: str = "",
    probability: float | None = None,
    force: bool = False,
) -> list[dict]:
    resolved_probability = TRIGGER_PROBABILITIES.get(trigger_reason, TRIGGER_PROBABILITIES["default"]) if probability is None else probability
    if not force and not should_refresh_recommendations(profile.id, trigger_reason, source_id, resolved_probability):
        return await get_home_recommendations(session, profile.id)

    candidates = await build_recommendation_candidates(session, profile)
    if not candidates:
        await archive_active_recommendations(session, profile.id)
        await session.flush()
        return []

    await archive_active_recommendations(session, profile.id)
    created: list[HomeRecommendation] = []
    for candidate in unique_candidates(candidates)[:4]:
        item = HomeRecommendation(
            user_id=profile.id,
            text=candidate.text[:160],
            reason=candidate.reason[:800],
            source_type=candidate.source_type or source_type,
            source_id=candidate.source_id or source_id,
            action_type=candidate.action_type,
            priority=candidate.priority,
            trigger_reason=trigger_reason,
        )
        session.add(item)
        created.append(item)
    await session.flush()
    return [serialize_recommendation(item) for item in created]


def should_refresh_recommendations(user_id: str, trigger_reason: str, source_id: str = "", probability: float = 0.35) -> bool:
    if probability <= 0:
        return False
    if probability >= 1:
        return True
    key = f"{user_id}:{trigger_reason}:{source_id}:{date.today().isoformat()}"
    ratio = int(sha256(key.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return ratio < probability


async def archive_active_recommendations(session: AsyncSession, user_id: str) -> None:
    await session.execute(
        update(HomeRecommendation)
        .where(HomeRecommendation.user_id == user_id, HomeRecommendation.status == "active")
        .values(status="superseded")
    )


async def build_recommendation_candidates(session: AsyncSession, profile: UserProfile) -> list[RecommendationCandidate]:
    actions = (
        await session.execute(
            select(ActionState)
            .where(ActionState.user_id == profile.id, ActionState.status == "pending")
            .order_by(ActionState.priority, desc(ActionState.updated_at))
            .limit(4)
        )
    ).scalars().all()
    issues = (
        await session.execute(
            select(GrowthIssue)
            .where(GrowthIssue.user_id == profile.id, GrowthIssue.status.in_(["new", "improving"]))
            .order_by(desc(GrowthIssue.updated_at))
            .limit(6)
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
    memories = (
        await session.execute(
            select(AgentMemory)
            .where(AgentMemory.user_id == profile.id)
            .order_by(desc(AgentMemory.updated_at))
            .limit(30)
        )
    ).scalars().all()
    knowledge = (
        await session.execute(
            select(KnowledgeResource)
            .where(KnowledgeResource.user_id == profile.id, KnowledgeResource.source == "personal")
            .order_by(desc(KnowledgeResource.created_at))
            .limit(4)
        )
    ).scalars().all()

    candidates: list[RecommendationCandidate] = []
    for action in actions:
        candidates.append(
            RecommendationCandidate(
                text=short_prompt(f"继续{action.title}"),
                reason=action.description or "来自待完成训练动作",
                source_type="action",
                source_id=action.id,
                action_type=action.action_type,
                priority=max(1, action.priority or 2),
            )
        )

    primary_issue = next(iter(issues), None)
    if primary_issue:
        candidates.append(
            RecommendationCandidate(
                text=short_prompt(f"再练练{primary_issue.title}"),
                reason=primary_issue.description,
                source_type="growth_issue",
                source_id=primary_issue.id,
                action_type="targeted_practice",
                priority=1,
            )
        )

    if profile.resume_text and len(profile.resume_text.strip()) >= 80:
        candidates.append(
            RecommendationCandidate(
                text="用新版简历练项目深挖",
                reason="用户已有可用简历，适合进入简历深挖训练。",
                source_type="resume",
                source_id=profile.id,
                action_type="mock_interview",
                priority=2,
            )
        )
        candidates.append(
            RecommendationCandidate(
                text="把简历亮点改成证据链",
                reason="已有简历内容，可继续优化量化结果、角色贡献和追问证据。",
                source_type="resume",
                source_id=profile.id,
                action_type="resume_optimization",
                priority=3,
            )
        )

    job_goal = first_memory(memories, {"job_goal", "target_company"})
    if job_goal and has_real_goal_signal(profile, job_goal):
        target = " ".join(item for item in [profile.target_company, profile.target_role] if item).strip() or "目标岗位"
        candidates.append(
            RecommendationCandidate(
                text=short_prompt(f"按{target}来一场 Mock"),
                reason=job_goal.content,
                source_type="memory",
                source_id=job_goal.id,
                action_type="mock_interview",
                priority=2,
            )
        )

    experience = first_memory(memories, {"project_signal", "resume_signal", "skill_signal", "profile_fact"})
    if experience:
        candidates.append(
            RecommendationCandidate(
                text="把核心经历整理成面试答案",
                reason=experience.content,
                source_type="memory",
                source_id=experience.id,
                action_type="profile_polish",
                priority=3,
            )
        )

    if knowledge:
        primary = knowledge[0]
        candidates.append(
            RecommendationCandidate(
                text="基于知识库生成追问题",
                reason=f"最近上传或整理了资料：{primary.title}",
                source_type="knowledge",
                source_id=primary.id,
                action_type="knowledge_qa",
                priority=3,
            )
        )

    if insights:
        candidates.append(
            RecommendationCandidate(
                text="把最近问题变成训练计划",
                reason=insights[0].content,
                source_type="growth_insight",
                source_id=insights[0].id,
                action_type="growth_plan",
                priority=3,
            )
        )

    return candidates


def first_memory(memories: list[AgentMemory], kinds: set[str]) -> AgentMemory | None:
    return next((item for item in memories if item.kind in kinds and memory_is_active(item)), None)


def memory_is_active(memory: AgentMemory) -> bool:
    metadata = memory.memory_metadata if isinstance(memory.memory_metadata, dict) else {}
    return str(metadata.get("status") or "active") not in {"archived", "superseded", "resolved"}


def has_real_goal_signal(profile: UserProfile, memory: AgentMemory) -> bool:
    if profile.target_company:
        return True
    if profile.target_role and profile.target_role != "产品经理":
        return True
    return len(memory.content.strip()) >= 24


def short_prompt(value: str, limit: int = 24) -> str:
    cleaned = " ".join(value.replace("\n", " ").split())
    return cleaned if len(cleaned) <= limit else f"{cleaned[:limit - 1]}…"


def unique_candidates(candidates: list[RecommendationCandidate]) -> list[RecommendationCandidate]:
    seen: set[str] = set()
    unique: list[RecommendationCandidate] = []
    for item in sorted(candidates, key=lambda candidate: candidate.priority):
        key = item.text.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def serialize_recommendation(item: HomeRecommendation) -> dict:
    return {
        "id": item.id,
        "text": item.text,
        "reason": item.reason,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "action_type": item.action_type,
        "priority": item.priority,
        "trigger_reason": item.trigger_reason,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
