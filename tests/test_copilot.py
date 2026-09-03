from pathlib import Path

import pytest

from backend.app.models import CandidateProfile, UserProfile
from backend.app.services.candidate_profile import ensure_candidate_profile
from backend.app.services.copilot import build_candidate_snapshot, generate_open_answer, map_form_fields, refine_mappings_with_agent, refresh_repeat_actions


class FakeCopilotAgent:
    def get_client(self):
        return object()

    async def json_complete(self, _messages, _fallback, allow_fallback=True):
        return {
            "mappings": [
                {
                    "field_id": "f1",
                    "candidate_path": "basics.phone",
                    "confidence": 0.91,
                    "reason": "字段语义表示紧急联系电话，和手机号码一致。",
                }
            ]
        }


@pytest.mark.asyncio
async def test_copilot_maps_common_fields_and_skips_sensitive_fields(db_session) -> None:
    profile = UserProfile(
        id="u-copilot",
        username="copilot-user",
        name="杨诗卉",
        target_role="AI 产品经理",
        target_company="字节跳动",
        resume_text=(
            "杨诗卉 152-8024-1298 2717316658@qq.com\n"
            "教育背景 北京航空航天大学 外国语言学及应用语言学专业 硕士 2024.09-2027.06\n"
            "实习经历 在字节做 AIGC 内容产品，负责需求分析、PRD 和数据复盘。\n"
            "项目经历 减肥搭子Agent项目，负责用户调研、产品方案、指标设计。\n"
            "获奖：互联网+ 校级一等奖\n"
            "技能 Figma Axure SQL Python Excel"
        ),
    )
    db_session.add(profile)
    candidate = await ensure_candidate_profile(db_session, profile, force=True, source="test")
    snapshot = build_candidate_snapshot(profile, candidate)

    preview = map_form_fields(
        [
            {"id": "f1", "tagName": "input", "inputType": "text", "label": "姓名", "selector": "#name"},
            {"id": "f2", "tagName": "input", "inputType": "tel", "label": "手机号码", "selector": "#phone"},
            {"id": "f3", "tagName": "input", "inputType": "email", "label": "邮箱", "selector": "#email"},
            {"id": "f4", "tagName": "input", "inputType": "text", "label": "毕业院校", "selector": "#school"},
            {"id": "f5", "tagName": "select", "inputType": "select", "label": "学历", "selector": "#degree"},
            {"id": "f6", "tagName": "input", "inputType": "text", "label": "专业", "selector": "#major"},
            {"id": "f7", "tagName": "textarea", "inputType": "textarea", "label": "项目描述", "selector": "#project"},
            {"id": "f8", "tagName": "input", "inputType": "password", "label": "密码", "selector": "#password"},
            {"id": "f9", "tagName": "input", "inputType": "text", "label": "验证码", "selector": "#captcha"},
            {"id": "f10", "tagName": "textarea", "inputType": "textarea", "label": "为什么申请这个岗位？", "selector": "#why"},
            {
                "id": "f11",
                "tagName": "input",
                "inputType": "search",
                "label": "",
                "nearbyText": "手机号码 暂无选项 个人信息 出生日期 籍贯 您了解到容知日新的主要渠道是",
                "selector": ".ant-select-selection-search-input",
            },
            {
                "id": "f12",
                "tagName": "input",
                "inputType": "text",
                "label": "",
                "nearbyText": "个人信息 姓名 手机号码 邮箱 出生日期 籍贯 主要渠道",
                "selector": ".custom-picker input",
            },
        ],
        snapshot,
        url="https://ats.example.com/apply",
    )

    mapped_ids = {item["field_id"] for item in preview["mappings"]}
    assert preview["skipped_count"] == 2
    assert {"f1", "f2", "f3", "f4", "f5", "f6", "f7"}.issubset(mapped_ids)
    assert "f8" not in mapped_ids
    assert "f9" not in mapped_ids
    assert preview["summary"]["direct_fill"] >= 6
    assert any(item["status"] == "ai_generated" for item in preview["mappings"])
    assert next(item for item in preview["mappings"] if item["field_id"] == "f7")["candidate_path"] == "projects.0.summary"
    assert next(item for item in preview["mappings"] if item["field_id"] == "f10")["mapping_type"] == "agent_draft"
    assert next(item for item in preview["mappings"] if item["field_id"] == "f2")["value"] == "15280241298"
    assert next(item for item in preview["mappings"] if item["field_id"] == "f11")["status"] == "unsupported"
    assert next(item for item in preview["mappings"] if item["field_id"] == "f12")["status"] == "unsupported"


@pytest.mark.asyncio
async def test_copilot_does_not_reuse_education_date_for_unrelated_basics(db_session) -> None:
    profile = UserProfile(
        id="u-copilot-ats",
        username="copilot-ats",
        name="杨诗卉",
        resume_text=(
            "杨诗卉 15280241298 2717316658@qq.com\n"
            "教育背景 北京航空航天大学 外国语言学及应用语言学专业 硕士 2024.09-2027.06"
        ),
    )
    db_session.add(profile)
    candidate = await ensure_candidate_profile(db_session, profile, force=True, source="test")
    snapshot = build_candidate_snapshot(profile, candidate)

    preview = map_form_fields(
        [
            {"id": "f1", "tagName": "input", "inputType": "text", "label": "出生日期", "selector": "#birth"},
            {"id": "f2", "tagName": "input", "inputType": "text", "label": "籍贯", "selector": "#hometown"},
            {"id": "f3", "tagName": "input", "inputType": "text", "label": "您了解到我们的主要渠道是", "selector": "#source"},
            {"id": "f4", "tagName": "input", "inputType": "text", "label": "入学时间", "selector": "#enroll"},
            {"id": "f5", "tagName": "input", "inputType": "text", "label": "开始时间", "selector": "#generic-start"},
            {"id": "f6", "tagName": "textarea", "inputType": "textarea", "label": "实习内容", "selector": "#internship-content"},
            {"id": "f7", "tagName": "textarea", "inputType": "textarea", "label": "单位介绍", "selector": "#org-intro"},
        ],
        snapshot,
    )

    by_id = {item["field_id"]: item for item in preview["mappings"]}
    assert by_id["f1"]["candidate_path"] == "basics.birth_date"
    assert by_id["f1"]["value"] == ""
    assert by_id["f2"]["candidate_path"] == "basics.hometown"
    assert by_id["f2"]["value"] == ""
    assert by_id["f3"]["candidate_path"] == "basics.source_channel"
    assert by_id["f3"]["value"] == ""
    assert by_id["f4"]["candidate_path"] in {"education.0.enrollment_year", "education.0.start_date"}
    assert by_id["f4"]["value"] == "2024.09"
    assert by_id["f5"]["status"] == "unsupported"
    assert by_id["f6"]["status"] == "ai_generated"
    assert by_id["f6"]["candidate_path"] == "agent_draft"
    assert by_id["f7"]["status"] == "ai_generated"


@pytest.mark.asyncio
async def test_copilot_open_answer_uses_profile_context_and_requires_review(db_session) -> None:
    profile = UserProfile(
        id="u-copilot-answer",
        username="copilot-answer",
        name="杨诗卉",
        target_role="AI 产品经理",
        resume_text="项目经历 减肥搭子Agent项目，负责需求调研、产品方案和数据复盘。技能 Figma SQL Python",
    )
    db_session.add(profile)
    candidate = await ensure_candidate_profile(db_session, profile, force=True, source="test")
    snapshot = build_candidate_snapshot(profile, candidate)

    answer = generate_open_answer("为什么申请这个岗位？", "负责 AI 产品策略和用户增长", snapshot)

    assert answer["needs_review"] is True
    assert "AI 产品经理" in answer["answer"]
    assert "减肥搭子Agent项目" in answer["answer"]


def test_extension_manifest_does_not_request_submit_power() -> None:
    manifest = Path("extension/manifest.json").read_text(encoding="utf-8")
    content = Path("extension/src/autofill/autofill.js").read_text(encoding="utf-8")

    assert '"activeTab"' in manifest
    assert "submit()" not in content
    assert "password" in content
    assert "captcha" in content


@pytest.mark.asyncio
async def test_copilot_agent_refines_low_confidence_mapping(db_session) -> None:
    profile = UserProfile(
        id="u-copilot-agent",
        username="copilot-agent",
        name="杨诗卉",
        resume_text="杨诗卉 15280241298 2717316658@qq.com",
    )
    db_session.add(profile)
    candidate = await ensure_candidate_profile(db_session, profile, force=True, source="test")
    snapshot = build_candidate_snapshot(profile, candidate)
    preview = map_form_fields(
        [
            {
                "id": "f1",
                "tagName": "input",
                "inputType": "text",
                "label": "紧急联系方式",
                "selector": "#urgent-phone",
            }
        ],
        snapshot,
    )

    refined = await refine_mappings_with_agent(preview, snapshot, FakeCopilotAgent(), domain="ats.example.com")
    item = refined["mappings"][0]

    assert refined["agent_status"] == "decided"
    assert item["mapping_type"] == "agent_decided"
    assert item["candidate_path"] == "basics.phone"
    assert item["value"] == "15280241298"
    assert item["status"] == "autofilled"


def test_copilot_expands_repeatable_experience_fields() -> None:
    profile = UserProfile(id="u-copilot-repeat", username="copilot-repeat", name="杨诗卉")
    candidate = CandidateProfile(
        user_id=profile.id,
        experiences=[
            {
                "title": "A科技公司 产品经理实习生",
                "summary": "2025.01-2025.03 在A科技公司担任产品经理实习生，负责需求分析和数据复盘。",
            },
            {
                "title": "B科技公司 AI产品实习生",
                "summary": "2025.04-2025.06 在B科技公司担任AI产品实习生，负责PRD撰写和原型设计。",
            },
        ],
        education=[],
        projects=[],
        skills=[],
        target_preferences={"role": "AI 产品经理"},
    )
    snapshot = build_candidate_snapshot(profile, candidate)

    preview = map_form_fields(
        [
            {"id": "f1", "tagName": "input", "inputType": "text", "label": "实习单位", "selector": "#company"},
            {"id": "f2", "tagName": "input", "inputType": "text", "label": "实习岗位", "selector": "#role"},
            {"id": "f3", "tagName": "textarea", "inputType": "textarea", "label": "实习内容", "selector": "#summary"},
        ],
        snapshot,
        repeaters=[{"id": "r1", "label": "添加实习经历", "selector": "#add-exp", "section": "experiences"}],
    )

    assert preview["repeat_actions"][0]["section"] == "experiences"
    assert preview["repeat_actions"][0]["times"] == 1
    repeated = [item for item in preview["mappings"] if item.get("mapping_type") == "repeat_expanded"]
    assert {item["candidate_path"] for item in repeated} >= {
        "experiences.1.company",
        "experiences.1.role",
        "experiences.1.summary",
    }
    assert all(item["status"] == "needs_confirmation" for item in repeated)


def test_copilot_maps_custom_controls_from_resume_snapshot() -> None:
    profile = UserProfile(
        id="u-copilot-custom-controls",
        username="copilot-custom-controls",
        name="杨诗卉",
        resume_text=(
            "杨诗卉 15280241298 2717316658@qq.com\n"
            "教育背景 北京航空航天大学 外国语言学及应用语言学专业 硕士 2024.09-2027.06\n"
            "英语六级 北京"
        ),
    )
    candidate = CandidateProfile(
        user_id=profile.id,
        education=[
            {
                "title": "北京航空航天大学 硕士",
                "summary": "北京航空航天大学 外国语言学及应用语言学专业 硕士 2024.09-2027.06",
            }
        ],
        experiences=[],
        projects=[],
        skills=[],
    )
    snapshot = build_candidate_snapshot(profile, candidate)

    preview = map_form_fields(
        [
            {"id": "f1", "tagName": "input", "inputType": "custom_select", "label": "最高学历", "selector": "#degree"},
            {"id": "f2", "tagName": "input", "inputType": "custom_select", "label": "最高学位", "selector": "#degree-level"},
            {"id": "f3", "tagName": "input", "inputType": "radio_group", "label": "应届/往届", "selector": "#graduate-type", "options": ["应届", "往届"]},
            {"id": "f4", "tagName": "input", "inputType": "custom_date", "label": "毕业时间", "selector": "#graduate-date"},
            {"id": "f5", "tagName": "textarea", "inputType": "textarea", "label": "自我评价", "selector": "#self-evaluation"},
            {"id": "f6", "tagName": "input", "inputType": "custom_select", "label": "英语等级", "selector": "#english"},
        ],
        snapshot,
    )

    by_id = {item["field_id"]: item for item in preview["mappings"]}
    assert by_id["f1"]["value"] == "硕士"
    assert by_id["f2"]["value"] == "硕士"
    assert by_id["f3"]["value"] == "应届"
    assert by_id["f4"]["value"] == "2027.06"
    assert by_id["f5"]["status"] == "ai_generated"
    assert by_id["f6"]["value"] in {"CET-6", "大学英语六级"}


def test_copilot_maps_manually_added_repeat_sections_without_clicking_add() -> None:
    profile = UserProfile(
        id="u-copilot-manual-repeat",
        username="copilot-manual-repeat",
        name="杨诗卉",
        resume_text="获奖：互联网+ 校级一等奖；挑战杯 校级二等奖",
    )
    candidate = CandidateProfile(
        user_id=profile.id,
        experiences=[],
        education=[],
        projects=[
            {"title": "减肥搭子Agent", "summary": "负责需求调研、PRD 和指标设计。"},
            {"title": "疗愈搭子Agent", "summary": "负责用户访谈、情绪场景拆解和功能设计。"},
        ],
        skills=[],
    )
    snapshot = build_candidate_snapshot(profile, candidate)

    preview = map_form_fields(
        [
            {"id": "f1", "tagName": "input", "inputType": "text", "label": "项目名称", "selector": "#project-title-1"},
            {"id": "f2", "tagName": "textarea", "inputType": "textarea", "label": "项目内容", "selector": "#project-summary-1"},
            {"id": "f3", "tagName": "input", "inputType": "text", "label": "项目名称", "selector": "#project-title-2"},
            {"id": "f4", "tagName": "textarea", "inputType": "textarea", "label": "项目内容", "selector": "#project-summary-2"},
            {"id": "f5", "tagName": "input", "inputType": "text", "label": "奖项名称", "selector": "#award-title-1"},
            {"id": "f6", "tagName": "input", "inputType": "text", "label": "奖项名称", "selector": "#award-title-2"},
        ],
        snapshot,
    )

    by_id = {item["field_id"]: item for item in preview["mappings"]}
    assert by_id["f1"]["candidate_path"] == "projects.0.title"
    assert by_id["f3"]["candidate_path"] == "projects.1.title"
    assert by_id["f4"]["candidate_path"] == "projects.1.summary"
    assert by_id["f5"]["candidate_path"] == "awards.0.title"
    assert by_id["f6"]["candidate_path"] == "awards.1.title"
    assert by_id["f3"]["value"] == "疗愈搭子Agent"
    assert "挑战杯" in by_id["f6"]["value"]


def test_copilot_binds_repeated_ai_drafts_to_each_experience() -> None:
    profile = UserProfile(id="u-copilot-draft-repeat", username="copilot-draft-repeat", name="杨诗卉")
    candidate = CandidateProfile(
        user_id=profile.id,
        experiences=[
            {"title": "字节跳动 AI产品经理", "summary": "在字节跳动负责 AIGC 素材链路改造和评测体系。"},
            {"title": "快手 产品实习生", "summary": "在快手负责 B 端商家工具需求分析和后台流程优化。"},
            {"title": "小红书 AIGC产品", "summary": "在小红书负责内容账号增长策略和创作者数据分析。"},
        ],
        education=[],
        projects=[],
        skills=[],
    )
    snapshot = build_candidate_snapshot(profile, candidate)
    preview = map_form_fields(
        [
            {"id": "f1", "tagName": "textarea", "inputType": "textarea", "label": "单位介绍", "selector": "#intro-1"},
            {"id": "f2", "tagName": "textarea", "inputType": "textarea", "label": "单位介绍", "selector": "#intro-2"},
            {"id": "f3", "tagName": "textarea", "inputType": "textarea", "label": "单位介绍", "selector": "#intro-3"},
        ],
        snapshot,
    )

    by_id = {item["field_id"]: item for item in preview["mappings"]}
    assert by_id["f1"]["status"] == "ai_generated"
    assert by_id["f1"]["candidate_path"] == "experiences.0.summary"
    assert by_id["f2"]["candidate_path"] == "experiences.1.summary"
    assert by_id["f3"]["candidate_path"] == "experiences.2.summary"

    answer = generate_open_answer("单位介绍", "", snapshot, candidate_path=by_id["f2"]["candidate_path"])
    assert "快手" in answer["answer"]
    assert "字节跳动负责 AIGC" not in answer["answer"]


@pytest.mark.asyncio
async def test_copilot_agent_decision_runs_before_repeat_expansion() -> None:
    class ProjectAgent:
        def get_client(self):
            return object()

        async def json_complete(self, _messages, _fallback, allow_fallback=True):
            return {
                "mappings": [
                    {
                        "field_id": "f1",
                        "candidate_path": "projects.0.title",
                        "confidence": 0.9,
                        "reason": "字段是项目名称，应映射到第一段项目经历。",
                    },
                    {
                        "field_id": "f2",
                        "candidate_path": "projects.0.summary",
                        "confidence": 0.9,
                        "reason": "字段是项目内容，应映射到第一段项目描述。",
                    },
                ]
            }

    profile = UserProfile(id="u-copilot-project-repeat", username="copilot-project-repeat", name="杨诗卉")
    candidate = CandidateProfile(
        user_id=profile.id,
        experiences=[],
        education=[],
        projects=[
            {"title": "减肥搭子Agent", "summary": "负责需求调研、PRD 和指标设计。"},
            {"title": "疗愈搭子Agent", "summary": "负责用户访谈、情绪场景拆解和功能设计。"},
        ],
        skills=[],
    )
    snapshot = build_candidate_snapshot(profile, candidate)
    preview = map_form_fields(
        [
            {"id": "f1", "tagName": "input", "inputType": "text", "label": "名称", "selector": "#title"},
            {"id": "f2", "tagName": "textarea", "inputType": "textarea", "label": "内容", "selector": "#summary"},
        ],
        snapshot,
    )

    refined = await refine_mappings_with_agent(preview, snapshot, ProjectAgent(), domain="ats.example.com")
    refreshed = refresh_repeat_actions(
        refined,
        snapshot,
        [{"id": "r1", "label": "添加项目经历", "selector": "#add-project", "section": "projects"}],
    )

    assert refreshed["repeat_actions"][0]["section"] == "projects"
    repeated = [item for item in refreshed["mappings"] if item.get("mapping_type") == "repeat_expanded"]
    assert {item["candidate_path"] for item in repeated} >= {"projects.1.title", "projects.1.summary"}
