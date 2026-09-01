from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    ApplicationState,
    CandidateProfile,
    InterviewSession,
    PeachTreeState,
    RewardEvent,
    UserProfile,
)


PEACH_REWARDS = {
    "profile_completed": {"xp": 20, "points": 10},
    "first_resume_uploaded": {"xp": 30, "points": 20},
    "application_completed": {"xp": 20, "points": 10},
    "mock_completed": {"xp": 50, "points": 25},
    "targeted_training_completed": {"xp": 30, "points": 15},
    "interview_review_completed": {"xp": 30, "points": 15},
    "daily_action_completed": {"xp": 20, "points": 10},
    "profile_material_completed": {"xp": 10, "points": 5},
}

TREE_STAGE_LABELS = {
    "seed": "种子",
    "sprout": "发芽",
    "seedling": "小苗",
    "tree": "成树",
    "blossom": "开花",
    "green_peach": "青桃",
    "mature": "成熟",
}

TREE_STAGE_ORDER = ["seed", "sprout", "seedling", "tree", "blossom", "green_peach", "mature"]


async def ensure_tree(session: AsyncSession, profile: UserProfile) -> PeachTreeState:
    tree = (
        await session.execute(select(PeachTreeState).where(PeachTreeState.user_id == profile.id).limit(1))
    ).scalar_one_or_none()
    if not tree:
        tree = PeachTreeState(user_id=profile.id, stage="seed", last_active_date=today_key())
        session.add(tree)
        await session.flush()
    return tree


async def award_once(
    session: AsyncSession,
    profile: UserProfile,
    event_type: str,
    source_id: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[RewardEvent | None, bool]:
    source = str(source_id or event_type)
    existing = (
        await session.execute(
            select(RewardEvent)
            .where(
                RewardEvent.user_id == profile.id,
                RewardEvent.event_type == event_type,
                RewardEvent.source_id == source,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        return existing, False

    config = PEACH_REWARDS.get(event_type, {"xp": 0, "points": 0})
    tree = await ensure_tree(session, profile)
    tree.growth_xp = max(0, (tree.growth_xp or 0) + int(config["xp"]))
    tree.peach_points = max(0, (tree.peach_points or 0) + int(config["points"]))
    tree.last_active_date = today_key()
    event = RewardEvent(
        user_id=profile.id,
        event_type=event_type,
        source_id=source,
        xp_delta=int(config["xp"]),
        points_delta=int(config["points"]),
        event_metadata=metadata or {},
    )
    session.add(event)
    await refresh_tree_stage(session, profile, tree)
    await session.flush()
    return event, True


async def refresh_tree_stage(session: AsyncSession, profile: UserProfile, tree: PeachTreeState | None = None) -> PeachTreeState:
    tree = tree or await ensure_tree(session, profile)
    candidate = (
        await session.execute(select(CandidateProfile).where(CandidateProfile.user_id == profile.id).limit(1))
    ).scalar_one_or_none()
    app_counts = await application_status_counts(session, profile.id)
    completed_mocks = int(
        await session.scalar(
            select(func.count(InterviewSession.id))
            .where(InterviewSession.user_id == profile.id, InterviewSession.status == "completed")
        )
        or 0
    )

    stage = "seed"
    if candidate and (candidate.completeness or 0) >= 55:
        stage = "sprout"
    if completed_mocks or app_counts["applied"] or app_counts["screening"] or app_counts["interview"] or app_counts["final"] or app_counts["offer"]:
        stage = "seedling"
    if (tree.growth_xp or 0) >= 120:
        stage = "tree"
    if app_counts["interview"]:
        stage = "blossom"
    if app_counts["final"]:
        stage = "green_peach"
    if app_counts["offer"]:
        stage = "mature"

    tree.stage = later_stage(tree.stage or "seed", stage)
    tree.last_active_date = tree.last_active_date or today_key()
    return tree


async def application_status_counts(session: AsyncSession, user_id: str) -> dict[str, int]:
    rows = (
        await session.execute(
            select(ApplicationState.status, func.count(ApplicationState.id))
            .where(ApplicationState.user_id == user_id)
            .group_by(ApplicationState.status)
        )
    ).all()
    counts = {status: int(count) for status, count in rows}
    for status in ["draft", "ready", "applied", "screening", "interview", "final", "offer", "rejected", "withdrawn"]:
        counts.setdefault(status, 0)
    return counts


def later_stage(current: str, candidate: str) -> str:
    current_index = TREE_STAGE_ORDER.index(current) if current in TREE_STAGE_ORDER else 0
    candidate_index = TREE_STAGE_ORDER.index(candidate) if candidate in TREE_STAGE_ORDER else 0
    return TREE_STAGE_ORDER[max(current_index, candidate_index)]


def serialize_tree(tree: PeachTreeState) -> dict[str, Any]:
    xp = tree.growth_xp or 0
    stage = tree.stage or "seed"
    next_stage = TREE_STAGE_ORDER[min(TREE_STAGE_ORDER.index(stage) + 1, len(TREE_STAGE_ORDER) - 1)] if stage in TREE_STAGE_ORDER else "sprout"
    return {
        "id": tree.id,
        "stage": stage,
        "stage_label": TREE_STAGE_LABELS.get(stage, stage),
        "next_stage": next_stage,
        "next_stage_label": TREE_STAGE_LABELS.get(next_stage, next_stage),
        "growth_xp": xp,
        "peach_points": tree.peach_points or 0,
        "progress": min(100, xp % 100 if stage != "mature" else 100),
        "streak_days": tree.streak_days or 0,
        "last_active_date": tree.last_active_date,
    }


def today_key() -> str:
    return date.today().isoformat()
