from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP

from backend.app.api.routes import (
    ChatIn,
    InterviewAnswerIn,
    InterviewStartIn,
    agent,
    answer_interview,
    build_interview_progress,
    chat,
    current_username,
    finish_interview,
    get_or_create_profile,
    relevant_memory_context,
    serialize_profile,
    start_interview,
)
from backend.app.db import SessionLocal
from backend.app.models import InterviewSession
from backend.app.services.memory import remember_interaction_isolated


REQUIRED_TOOLS = {
    "peach_chat",
    "peach_start_interview",
    "peach_answer_interview",
    "peach_finish_interview",
    "peach_generate_resume",
    "peach_profile_snapshot",
}


peach_mcp = FastMCP(
    "Peach Interview Companion",
    instructions=(
        "桃子是面向产品经理求职者的个性化求职陪练 Agent。"
        "工具支持求职咨询、模拟面试、面试复盘和简历生成。"
        "username 用于 Demo 账号隔离，不需要密码。"
    ),
    host="0.0.0.0",
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
)


def _error(exc: Exception) -> dict:
    trace_id = str(uuid4())
    if isinstance(exc, HTTPException):
        return {"ok": False, "error": str(exc.detail), "status_code": exc.status_code, "trace_id": trace_id}
    return {"ok": False, "error": str(exc), "trace_id": trace_id}


async def _with_user(username: str, handler):
    token = current_username.set((username or "demo").strip()[:40] or "demo")
    try:
        async with SessionLocal() as session:
            return await handler(session)
    except Exception as exc:
        return _error(exc)
    finally:
        current_username.reset(token)


@peach_mcp.tool()
async def peach_chat(username: str, message: str) -> dict:
    """和桃子进行一次个性化求职咨询，会读取并更新该 username 的长期记忆。"""

    async def run(session):
        result = await chat(ChatIn(message=message), session)
        return {"ok": True, **result}

    return await _with_user(username, run)


@peach_mcp.tool()
async def peach_start_interview(
    username: str,
    company: str = "",
    role: str = "产品经理",
    jd: str = "",
    interviewer_style: str = "温和型",
    interview_type: str = "模拟面试",
    question_bank: str = "",
) -> dict:
    """创建一场模拟面试，返回 interview_id、开场语、第一题和面试进度。"""

    async def run(session):
        payload = InterviewStartIn(
            interview_type=interview_type or "模拟面试",
            interviewer_style=interviewer_style or "温和型",
            company=company,
            role=role or "产品经理",
            jd=jd,
            question_bank=question_bank,
        )
        result = await start_interview(payload, session)
        return {"ok": True, **result}

    return await _with_user(username, run)


@peach_mcp.tool()
async def peach_answer_interview(username: str, interview_id: str, answer: str) -> dict:
    """向一场进行中的模拟面试提交候选人回答，并返回下一道面试官追问。"""

    async def run(session):
        result = await answer_interview(interview_id, InterviewAnswerIn(answer=answer), session)
        return {"ok": True, **result}

    return await _with_user(username, run)


@peach_mcp.tool()
async def peach_finish_interview(username: str, interview_id: str = "") -> dict:
    """结束指定或最近一场模拟面试，并生成结构化面试复盘报告。"""

    async def run(session):
        profile = await get_or_create_profile(session)
        target_id = interview_id.strip()
        if not target_id:
            from backend.app.api.routes import latest_interview

            latest = await latest_interview(session, profile.id, active_only=True)
            if not latest:
                latest = await latest_interview(session, profile.id, active_only=False)
            if not latest:
                raise HTTPException(status_code=404, detail="没有可结束的面试")
            target_id = latest.id
        result = await finish_interview(target_id, session)
        return {"ok": True, **result}

    return await _with_user(username, run)


@peach_mcp.tool()
async def peach_generate_resume(
    username: str,
    target_role: str = "产品经理",
    target_company: str = "",
    requirements: str = "",
    save_to_profile: bool = True,
) -> dict:
    """基于用户档案、长期记忆和目标岗位生成简历草稿，可选择保存到个人档案。"""

    async def run(session):
        profile = await get_or_create_profile(session)
        query = "\n".join([target_role, target_company, requirements, profile.resume_text or ""])
        memory_context = await relevant_memory_context(session, profile, query)
        fallback = (
            f"{profile.name}｜{target_role}\n\n"
            "教育背景：请补充学校、专业、时间和关键课程。\n\n"
            "项目经历：请按 背景、目标、行动、结果 写 2-3 段经历，并补充可量化指标。\n\n"
            "技能与优势：突出用户研究、需求分析、数据分析、跨团队协作和 AI 产品理解。"
        )
        prompt = f"""
请为用户生成一份面向目标岗位的中文产品经理简历草稿。
目标岗位：{target_role}
目标公司：{target_company or "未指定"}
用户要求：{requirements or "无"}
用户档案：{serialize_profile(profile)}
长期记忆：{memory_context[:1600] or "暂无"}
已有简历：{(profile.resume_text or "")[:5000] or "暂无"}

要求：
1. 输出可直接粘贴进简历的正文，不要 markdown 表格。
2. 强调真实经历、项目贡献、量化结果和岗位匹配。
3. 信息不足处用“待补充”，不要编造公司、学校、数据。
"""
        resume = await agent.complete([{"role": "user", "content": prompt}], fallback)
        if save_to_profile:
            profile.target_role = target_role or profile.target_role
            profile.target_company = target_company or profile.target_company
            profile.resume_text = resume
            await session.commit()
            await session.refresh(profile)
            await remember_interaction_isolated(
                agent,
                user_id=profile.id,
                username=profile.username,
                profile_snapshot={
                    "name": profile.name,
                    "target_role": profile.target_role,
                    "target_company": profile.target_company,
                    "target_city": profile.target_city,
                    "stage": profile.stage,
                    "resume_text": profile.resume_text,
                    "communication_style": profile.communication_style,
                    "strengths": list(profile.strengths or []),
                    "weak_points": list(profile.weak_points or []),
                    "plan": list(profile.plan or []),
                },
                source="mcp_resume_generation",
                user_message=f"生成简历：{target_company} {target_role}\n{requirements}",
                assistant_reply=resume,
                context={"memory_context_used": memory_context},
            )
        return {"ok": True, "resume": resume, "saved": save_to_profile, "profile": serialize_profile(profile)}

    return await _with_user(username, run)


@peach_mcp.tool()
async def peach_profile_snapshot(username: str) -> dict:
    """读取某个 Demo 用户的个人档案、最近记忆和最近面试概况，用于验证账号隔离和长期记忆。"""

    async def run(session):
        profile = await get_or_create_profile(session)
        from backend.app.api.routes import list_recent_memories, serialize_memory
        from sqlalchemy import desc, select

        memories = await list_recent_memories(session, profile.id, 8)
        result = await session.execute(
            select(InterviewSession)
            .where(InterviewSession.user_id == profile.id)
            .order_by(desc(InterviewSession.created_at))
            .limit(3)
        )
        interviews = result.scalars().all()
        return {
            "ok": True,
            "profile": serialize_profile(profile),
            "memories": [serialize_memory(item) for item in memories],
            "recent_interviews": [
                {
                    "id": item.id,
                    "company": item.company,
                    "role": item.role,
                    "status": item.status,
                    "progress": build_interview_progress(item),
                }
                for item in interviews
            ],
        }

    return await _with_user(username, run)
