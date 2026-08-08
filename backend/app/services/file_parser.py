from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".md", ".markdown", ".html", ".htm"}


@dataclass
class ParsedFile:
    filename: str
    extension: str
    title: str
    content: str
    summary: str
    warning: str = ""


def parse_upload(filename: str, content: bytes) -> ParsedFile:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("unsupported file type")

    warning = ""
    if extension == ".pdf":
        text = parse_pdf(content)
    elif extension == ".docx":
        text = parse_docx(content)
    elif extension == ".doc":
        text = parse_doc_binary_best_effort(content)
        warning = "老版 doc 文件采用基础文本抽取，复杂排版可能不完整。"
    elif extension in {".html", ".htm"}:
        text = parse_html(content)
    else:
        text = parse_markdown(content)

    title = file_title(filename, text)
    clean = normalize_text(text)
    return ParsedFile(
        filename=filename,
        extension=extension.lstrip("."),
        title=title,
        content=clean,
        summary=summarize(clean),
        warning=warning,
    )


def parse_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages)


def parse_docx(content: bytes) -> str:
    document = Document(io.BytesIO(content))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def parse_doc_binary_best_effort(content: bytes) -> str:
    if zipfile.is_zipfile(io.BytesIO(content)):
        return parse_docx(content)
    decoded = content.decode("utf-8", errors="ignore")
    if len(decoded.strip()) < 40:
        decoded = content.decode("gb18030", errors="ignore")
    strings = re.findall(r"[\u4e00-\u9fffA-Za-z0-9，。！？；：、,.!?;:()\[\]《》“”\"'\s]{3,}", decoded)
    return "\n".join(item.strip() for item in strings if item.strip())


def parse_html(content: bytes) -> str:
    raw = content.decode("utf-8", errors="ignore")
    if not raw.strip():
        raw = content.decode("gb18030", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n")


def parse_markdown(content: bytes) -> str:
    raw = content.decode("utf-8", errors="ignore")
    if not raw.strip():
        raw = content.decode("gb18030", errors="ignore")
    raw = re.sub(r"```[\s\S]*?```", " ", raw)
    raw = re.sub(r"`([^`]+)`", r"\1", raw)
    raw = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", raw)
    raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw)
    raw = re.sub(r"^\s{0,3}#{1,6}\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"^\s*[-*+]\s+", "", raw, flags=re.MULTILINE)
    return raw


def normalize_text(value: str) -> str:
    text = unescape(value)
    text = text.replace("\u00a0", " ")
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def summarize(value: str, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", value).strip()
    if not clean:
        return "文件已解析，但没有提取到有效文本。"
    return clean[:limit] + ("..." if len(clean) > limit else "")


def file_title(filename: str, content: str) -> str:
    stem = Path(filename).stem.strip()
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    if first_line and len(first_line) <= 40:
        return first_line
    return stem or "上传文件"
