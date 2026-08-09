from types import SimpleNamespace

from backend.app.api.routes import build_interview_progress, normalize_tool_action, normalize_username


def test_new_interview_has_zero_completion() -> None:
    interview = SimpleNamespace(transcript=[{"role": "interviewer", "content": "请先做自我介绍。"}])

    progress = build_interview_progress(interview)

    assert progress["answer_count"] == 0
    assert progress["completion"] == 0
    assert not progress["can_llm_finish"]
    assert all(not item["done"] for item in progress["checklist"])


def test_interview_cannot_finish_before_minimum_rounds() -> None:
    interview = SimpleNamespace(
        transcript=[
            {"role": "candidate", "content": "我是北航学生，做过 AI 产品项目。"},
            {"role": "candidate", "content": "我负责需求分析，推动上线，转化率提升 8%。"},
            {"role": "candidate", "content": "我理解产品经理要兼顾用户、业务和指标。"},
        ]
    )

    progress = build_interview_progress(interview)

    assert progress["answer_count"] == 3
    assert progress["completion"] > 0
    assert not progress["can_llm_finish"]


def test_tool_action_normalization_rejects_unknown_tool() -> None:
    action = normalize_tool_action({"tool": "drop_database", "payload": {"danger": True}}, 0)

    assert action["tool"] == "unsupported"
    assert action["approval_required"]
    assert action["payload"] == {}


def test_username_is_trimmed_and_bounded() -> None:
    assert normalize_username("  Apple01  ") == "Apple01"
    assert normalize_username("") == "demo"
    assert len(normalize_username("x" * 80)) == 40
