"""A Word document from a job: the text a person would want to read, with the
same honesty rules as the other exports — a poorly read page carries its
notes, corrections are applied, running headers and footers are left out.

Layout: the title, an italic line saying where it came from, then each page:
its quality notes in italics if any, headings as Heading 2, body lines joined
into paragraphs at the paragraph breaks the layout found, and a page break
between pages. Provenance goes into the file's core properties too.
"""

from __future__ import annotations

import io

from .checks import quality_note
from .corrections import Corrections
from .settings import Settings


def _paragraphs(lines) -> list[tuple[str, str]]:
    """(kind, text) runs: 'heading' lines stand alone; body lines are joined
    with spaces until a paragraph break or a heading."""
    out: list[tuple[str, str]] = []
    body: list[str] = []

    def flush():
        if body:
            out.append(("body", " ".join(body)))
            body.clear()

    for ln in lines:
        if ln.heading:
            flush()
            out.append(("heading", ln.text))
            continue
        if ln.para_break_before:
            flush()
        body.append(ln.text)
    flush()
    return out


def build_docx(
    title: str, records, total: int, settings: Settings, corrections: Corrections | None = None
) -> bytes:
    from docx import Document
    from docx.shared import Pt

    from . import __version__

    corrections = corrections or Corrections()
    doc = Document()
    doc.styles["Normal"].font.size = Pt(11)
    doc.add_heading(title, level=0)
    preamble = doc.add_paragraph()
    preamble.add_run(
        f"Transcribed locally by UsefulText {__version__} (RapidOCR). Read quality is the OCR "
        f"engine's own certainty, not a measure of accuracy. {len(records)} of {total} pages read."
    ).italic = True

    for i, rec in enumerate(records):
        if i > 0:
            doc.add_page_break()
        for note in quality_note(rec):
            doc.add_paragraph().add_run(f"[{note}]").italic = True
        if rec.status != "done":
            continue
        for kind, text in _paragraphs(rec.text_lines(settings.strip_furniture, corrections)):
            if kind == "heading":
                doc.add_heading(text, level=2)
            else:
                doc.add_paragraph(text)

    props = doc.core_properties
    props.title = title
    props.author = "UsefulText"
    corrected = sum(corrections.count(r) for r in records if r.status == "done")
    props.comments = (
        f"Transcribed by UsefulText {__version__} from photographed pages; "
        f"{corrected} lines corrected by hand."
    )
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
