from backend.app.services.file_parser import parse_upload


def test_parse_markdown_extracts_readable_text() -> None:
    parsed = parse_upload(
        "resume.md",
        b"# Project\n\n- Built [Peach](https://example.com) for interview practice.\n```js\nhidden()\n```",
    )

    assert parsed.extension == "md"
    assert "Project" in parsed.content
    assert "Peach" in parsed.content
    assert "hidden" not in parsed.content


def test_parse_html_strips_scripts() -> None:
    parsed = parse_upload(
        "jd.html",
        "<html><head><title>AI PM JD</title><script>bad()</script></head><body><h1>AI 产品经理</h1><p>负责 AIGC 产品策略。</p></body></html>".encode(),
    )

    assert parsed.extension == "html"
    assert parsed.title == "AI PM JD"
    assert "AI 产品经理" in parsed.content
    assert "负责 AIGC 产品策略" in parsed.content
    assert "bad()" not in parsed.content
