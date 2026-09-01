from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import ActionState, ApplicationState, DailyAction, GrowthIssue, UserProfile
from backend.app.services.rewards import award_once, refresh_tree_stage


DAILY_ACTION_STATUSES = {"pending", "started", "completed", "skipped"}


async def build_job_weather(session: AsyncSession, profile: UserProfile) -> dict[str, Any]:
    applications = (
        await session.execute(
            select(ApplicationState)
            .where(ApplicationState.user_id == profile.id)
            .order_by(desc(ApplicationState.updated_at))
            .limit(50)
        )
    ).scalars().all()
    issues = (
        await session.execute(
            select(GrowthIssue)
            .where(GrowthIssue.user_id == profile.id, GrowthIssue.status.in_(["new", "improving"]))
            .order_by(desc(GrowthIssue.occurrence_count), desc(GrowthIssue.updated_at))
            .limit(3)
        )
    ).scalars().all()

    interviewing = [item for item in applications if item.status in {"interview", "final"}]
    waiting = [item for item in applications if item.status in {"applied", "screening"}]
    ready = [item for item in applications if item.status == "ready"]
    offers = [item for item in applications if item.status == "offer"]

    if offers:
        weather, label = "sunny", "晴"
        summary = f"{offers[0].company or '目标公司'} 已进入 Offer 阶段，今天适合做选择和谈薪准备。"
    elif interviewing:
        weather, label = "partly_cloudy", "多云转晴"
        summary = f"{interviewing[0].company or '目标公司'} 正在面试中，今天优先准备目标公司追问。"
    elif waiting and len(waiting) >= 3:
        weather, label = "cloudy", "阴"
        summary = "近期投递较集中但还在等待反馈，今天适合复盘岗位匹配和补一场目标 Mock。"
    elif ready:
        weather, label = "partly_cloudy", "有云"
        summary = f"{ready[0].company or '目标公司'} 已准备好，今天最值得把这份投递收尾。"
    elif issues:
        weather, label = "cloudy", "阴转晴"
        summary = f"最近暴露出「{issues[0].title}」，今天做一个短训练会比泛泛焦虑更有效。"
    else:
        weather, label = "sunny", "晴"
        summary = "目前没有紧急节点，适合轻量补齐简历、档案或做一次基础 Mock。"

    return {
        "weather": weather,
        "label": label,
        "summary": summary,
        "reason": "基于投递状态、最近面试复盘和成长问题生成，仅作行动提醒，不代表真实录取概率。",
        "application_count": len(applications),
        "interviewing_count": len(interviewing),
        "waiting_count": len(waiting),
        "issue_count": len(issues),
    }


async def ensure_daily_action(session: AsyncSession, profile: UserProfile, *, force_new: bool = False) -> DailyAction:
    today = today_key()
    existing = (
        await session.execute(
            select(DailyAction)
            .where(DailyAction.user_id == profile.id, DailyAction.date == today)
            .order_by(desc(DailyAction.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing and not force_new:
        return existing

    action_data = await choose_daily_action(session, profile)
    action = DailyAction(user_id=profile.id, date=today, **action_data)
    session.add(action)
    await session.flush()
    return action


async def update_daily_action(session: AsyncSession, profile: UserProfile, action_id: str, status: str) -> DailyAction:
    if status not in DAILY_ACTION_STATUSES:
        raise HTTPException(status_code=400, detail="invalid daily action status")
    action = await session.get(DailyAction, action_id)
    if not action or action.user_id != profile.id:
        raise HTTPException(status_code=404, detail="daily action not found")
    action.status = status
    if status == "completed":
        action.completed_at = datetime.now(timezone.utc)
        await award_once(
            session,
            profile,
            "daily_action_completed",
            action.id,
            {"action_type": action.action_type, "title": action.title},
        )
    await refresh_tree_stage(session, profile)
    return action


async def choose_daily_action(session: AsyncSession, profile: UserProfile) -> dict[str, Any]:
    interview_app = (
        await session.execute(
            select(ApplicationState)
            .where(ApplicationState.user_id == profile.id, ApplicationState.status.in_(["interview", "final"]))
            .order_by(desc(ApplicationState.updated_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if interview_app:
        return {
            "action_type": "target_company_mock",
            "title": f"准备 {interview_app.company or '目标公司'} {interview_app.role or profile.target_role} 面试",
            "description": "围绕目标公司、岗位 JD 和你的项目经历做一轮 20 分钟追问。",
            "source_type": "application",
            "source_id": interview_app.id,
        }

    growth_action = (
        await session.execute(
            select(ActionState)
            .where(ActionState.user_id == profile.id, ActionState.status == "pending")
            .order_by(ActionState.priority, desc(ActionState.updated_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if growth_action:
        return {
            "action_type": "growth_training",
            "title": growth_action.title,
            "description": growth_action.description or "做一轮专项训练，把最近反复出现的问题练顺。",
            "source_type": "growth_action",
            "source_id": growth_action.id,
        }

    ready_app = (
        await session.execute(
            select(ApplicationState)
            .where(ApplicationState.user_id == profile.id, ApplicationState.status == "ready")
            .order_by(desc(ApplicationState.updated_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if ready_app:
        return {
            "action_type": "application_submit",
            "title": f"完成 {ready_app.company or '目标公司'} 投递",
            "description": "检查候选人信息、简历版本和开放题后，手动提交这份网申。",
            "source_type": "application",
            "source_id": ready_app.id,
        }

    return {
        "action_type": "light_restart",
        "title": "补齐一处简历证据",
        "description": "选一段项目或实习经历，补上背景、你的动作、可量化结果和一个可追问细节。",
        "source_type": "profile",
        "source_id": profile.id,
    }


def serialize_daily_action(action: DailyAction) -> dict[str, Any]:
    return {
        "id": action.id,
        "date": action.date,
        "action_type": action.action_type,
        "title": action.title,
        "description": action.description,
        "source_type": action.source_type,
        "source_id": action.source_id,
        "status": action.status,
        "created_at": action.created_at.isoformat() if action.created_at else None,
        "completed_at": action.completed_at.isoformat() if action.completed_at else None,
    }


def today_key() -> str:
    return date.today().isoformat()
