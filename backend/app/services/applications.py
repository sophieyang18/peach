from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import ApplicationState, UserProfile
from backend.app.services.rewards import award_once, refresh_tree_stage


APPLICATION_STATUSES = {"draft", "ready", "applied", "screening", "interview", "final", "offer", "rejected", "withdrawn"}
STATUS_ORDER = {
    "ready": 0,
    "interview": 1,
    "final": 2,
    "screening": 3,
    "applied": 4,
    "draft": 5,
    "offer": 6,
    "rejected": 7,
    "withdrawn": 8,
}


async def list_applications(session: AsyncSession, profile: UserProfile) -> dict[str, Any]:
    items = (
        await session.execute(
            select(ApplicationState)
            .where(ApplicationState.user_id == profile.id)
            .order_by(desc(ApplicationState.updated_at))
        )
    ).scalars().all()
    sorted_items = sorted(items, key=lambda item: STATUS_ORDER.get(item.status, 9))
    return {
        "items": [serialize_application(item) for item in sorted_items],
        "summary": application_summary(sorted_items),
    }


async def create_application(session: AsyncSession, profile: UserProfile, payload) -> ApplicationState:
    status = normalize_status(payload.status)
    item = ApplicationState(
        user_id=profile.id,
        company=short_text(payload.company or profile.target_company, 120),
        role=short_text(payload.role or profile.target_role, 120),
        jd_text=str(payload.jd_text or "")[:8000],
        source_url=str(payload.source_url or "")[:1000],
        resume_version_id=str(payload.resume_version_id or "")[:36],
        status=status,
        source=short_text(payload.source or "manual", 60),
        notes=str(payload.notes or "")[:4000],
    )
    stamp_status_time(item, "", status)
    session.add(item)
    await session.flush()
    await apply_application_side_effects(session, profile, item, "", status)
    return item


async def patch_application(session: AsyncSession, profile: UserProfile, application_id: str, payload) -> ApplicationState:
    item = await owned_application(session, profile.id, application_id)
    previous_status = item.status
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if key == "status":
            item.status = normalize_status(value)
        elif key in {"company", "role", "source", "resume_version_id"}:
            setattr(item, key, short_text(value, 120))
        elif key in {"jd_text", "source_url", "notes"}:
            setattr(item, key, str(value)[:8000])
    stamp_status_time(item, previous_status, item.status)
    await apply_application_side_effects(session, profile, item, previous_status, item.status)
    await session.flush()
    return item


async def delete_application(session: AsyncSession, profile: UserProfile, application_id: str) -> bool:
    item = await owned_application(session, profile.id, application_id)
    await session.delete(item)
    await session.flush()
    return True


async def owned_application(session: AsyncSession, user_id: str, application_id: str) -> ApplicationState:
    item = await session.get(ApplicationState, application_id)
    if not item or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="application not found")
    return item


async def apply_application_side_effects(
    session: AsyncSession,
    profile: UserProfile,
    item: ApplicationState,
    previous_status: str,
    next_status: str,
) -> None:
    if next_status in {"applied", "screening", "interview", "final", "offer"} and previous_status != next_status:
        await award_once(
            session,
            profile,
            "application_completed",
            item.id,
            {"company": item.company, "role": item.role, "status": next_status},
        )
    await refresh_tree_stage(session, profile)


def stamp_status_time(item: ApplicationState, previous_status: str, next_status: str) -> None:
    if previous_status == next_status:
        return
    now = datetime.now(timezone.utc)
    if next_status in {"applied", "screening"} and not item.applied_at:
        item.applied_at = now
    if next_status in {"interview", "final"} and not item.interview_at:
        item.interview_at = now
    if next_status == "rejected" and not item.rejected_at:
        item.rejected_at = now
    if next_status == "offer" and not item.offer_at:
        item.offer_at = now


def serialize_application(item: ApplicationState) -> dict[str, Any]:
    return {
        "id": item.id,
        "company": item.company,
        "role": item.role,
        "jd_text": item.jd_text,
        "source_url": item.source_url,
        "resume_version_id": item.resume_version_id,
        "status": item.status,
        "status_label": status_label(item.status),
        "source": item.source,
        "notes": item.notes,
        "next_step": next_step(item.status),
        "applied_at": item.applied_at.isoformat() if item.applied_at else None,
        "interview_at": item.interview_at.isoformat() if item.interview_at else None,
        "rejected_at": item.rejected_at.isoformat() if item.rejected_at else None,
        "offer_at": item.offer_at.isoformat() if item.offer_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def application_summary(items: list[ApplicationState]) -> dict[str, int]:
    counts = {status: 0 for status in APPLICATION_STATUSES}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    return {
        "total": len(items),
        "applied": sum(counts.get(status, 0) for status in ["applied", "screening", "interview", "final", "offer", "rejected"]),
        "waiting": sum(counts.get(status, 0) for status in ["applied", "screening"]),
        "interviewing": sum(counts.get(status, 0) for status in ["interview", "final"]),
        "offer": counts.get("offer", 0),
    }


def normalize_status(value: str) -> str:
    status = str(value or "draft").strip().lower()
    if status not in APPLICATION_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid application status: {value}")
    return status


def status_label(status: str) -> str:
    return {
        "draft": "草稿",
        "ready": "待投递",
        "applied": "已投递",
        "screening": "筛选中",
        "interview": "面试中",
        "final": "终面",
        "offer": "Offer",
        "rejected": "已拒绝",
        "withdrawn": "已撤回",
    }.get(status, status)


def next_step(status: str) -> str:
    return {
        "draft": "补齐 JD、简历版本和开放题材料",
        "ready": "确认信息后手动完成投递",
        "applied": "记录反馈，准备目标公司 Mock",
        "screening": "等待反馈，同时复盘岗位匹配",
        "interview": "优先准备这家公司的一面追问",
        "final": "准备业务复盘、反问和终面动机",
        "offer": "整理 offer 对比和入职决策",
        "rejected": "复盘失败原因，不自动归因为能力差",
        "withdrawn": "如仍感兴趣，可之后重新创建投递",
    }.get(status, "继续跟进")


def short_text(value: str, limit: int) -> str:
    clean = " ".join(str(value or "").split())
    return clean[:limit]
