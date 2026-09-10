import io

from docx import Document

from usefultext.corrections import Corrections
from usefultext.docx_export import build_docx
from usefultext.settings import Settings


def test_docx_has_headings_paragraphs_notes_and_corrections(make_record):
    a = make_record(
        page=1,
        id="p1",
        label="a.jpg",
        lines=[
            ("Chapter One", 200, True),
            ("The iceberg was me1ting.", 300),
            ("Nobody noticed.", 360),
        ],
    )
    a.lines[2]["para_break_before"] = True
    b = make_record(
        page=2,
        id="p2",
        label="b.jpg",
        lines=[("OUR ICEBERG | 7", 60), ("Second page text.", 300)],
        blurry=True,
        sharpness=50.0,
    )
    b.lines[0]["furniture"] = True
    c = Corrections()
    c.set("p1", 1, "The iceberg was melting.", "The iceberg was me1ting.")

    data = build_docx("Our Iceberg", [a, b], 2, Settings(), c)
    doc = Document(io.BytesIO(data))
    paras = [(p.style.name, p.text) for p in doc.paragraphs if p.text]
    assert paras[0] == ("Title", "Our Iceberg")
    assert "Transcribed locally by UsefulText" in paras[1][1]
    assert ("Heading 2", "Chapter One") in paras
    assert (
        "Normal",
        "The iceberg was melting.",
    ) in paras  # the correction, its own paragraph before the break
    assert ("Normal", "Nobody noticed.") in paras
    assert any(t.startswith("[The photo looks blurry") for _, t in paras)
    assert not any("OUR ICEBERG | 7" in t for _, t in paras)  # furniture stays out
    assert ("Normal", "Second page text.") in paras
    assert (
        doc.core_properties.title == "Our Iceberg"
        and "1 lines corrected" in doc.core_properties.comments
    )
    body_xml = doc.element.body.xml
    assert body_xml.count('w:type="page"') == 1  # one page break between the two pages
