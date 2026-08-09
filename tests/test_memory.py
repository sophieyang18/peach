from types import SimpleNamespace

from backend.app.services.memory import build_memory_context, is_valid_memory_content, tokenize


def test_memory_context_is_compact_and_labeled() -> None:
    memories = [
        SimpleNamespace(kind="job_goal", content="用户目标是 AI 产品经理。", tags=["目标"], use_count=0),
        SimpleNamespace(kind="weakness", content="用户面试时容易缺少量化结果。", tags=["面试"], use_count=0),
    ]

    context = build_memory_context(memories)

    assert "[求职目标]" in context
    assert "[薄弱点]" in context
    assert len(context) < 1200


def test_memory_filters_sensitive_or_low_value_content() -> None:
    assert is_valid_memory_content("用户目标是北京互联网公司的 AI 产品经理岗位。")
    assert not is_valid_memory_content("密码是 abc123456")
    assert not is_valid_memory_content("短")


def test_tokenize_supports_chinese_and_latin_terms() -> None:
    terms = tokenize("AIGC 产品经理 面试")

    assert "aigc" in terms
    assert "产品" in terms
    assert "面试" in terms
