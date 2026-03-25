"""
Document parsers for the RAG indexer.
Supported: .pdf, .docx, .txt, .md, .csv
"""
import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv"}


def parse_file(path: str) -> str:
    """Parse a file to plain text. Raises ValueError for unsupported types."""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return _parse_pdf(path)
    elif ext == ".docx":
        return _parse_docx(path)
    elif ext in (".txt", ".md"):
        return _parse_text(path)
    elif ext == ".csv":
        return _parse_csv(path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _parse_pdf(path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
            if text and text.strip():
                pages.append(text.strip())
        except Exception as e:
            logger.warning("Could not extract page %d from %s: %s", i, path, e)
    return "\n\n".join(pages)


def _parse_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _parse_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _parse_csv(path: str) -> str:
    """Convert CSV rows to readable key: value lines."""
    rows: list[list[str]] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return ""
    header = rows[0]
    lines = []
    for row in rows[1:]:
        pairs = "; ".join(
            f"{h.strip()}: {v.strip()}"
            for h, v in zip(header, row)
            if v.strip()
        )
        if pairs:
            lines.append(pairs)
    return "\n".join(lines)
