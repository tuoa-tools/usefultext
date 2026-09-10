import json

from usefultext.corrections import Corrections
from usefultext.inputs import PageSource
from usefultext.outputs import REPORT_COLUMNS, JobState, page_file_name, provenance, write_outputs
from usefultext.settings import Settings


def _job(tmp_path, make_record, labels):
    sources = [
        PageSource(tmp_path / "photos" / lb, base=tmp_path, id=f"p{i + 1}")
        for i, lb in enumerate(labels)
    ]
    state = JobState(title="Test")
    for i, s in enumerate(sources, 1):
        lines = [("Chapter", 200, True), (f"Body of {s.label}", 300), ("More body.", 360)]
        state.pages[s.key] = make_record(
            page=i, label=s.label, id=s.page_id, key=s.key, lines=lines
        )
    return sources, state


def test_page_files_named_by_position_and_photo_and_cleaned_on_reorder(tmp_path, make_record):
    sources, state = _job(tmp_path, make_record, ["IMG_0042.jpg", "IMG_0043.jpg"])
    write_outputs(tmp_path, state, sources, Settings())
    names = sorted(p.name for p in (tmp_path / "pages").glob("*.txt"))
    assert names == ["page_001_IMG_0042.txt", "page_002_IMG_0043.txt"]
    first = (tmp_path / "pages" / "page_001_IMG_0042.txt").read_text(encoding="utf-8").splitlines()
    assert first[0] == "[page 1 of 2 · IMG_0042.jpg · read quality 0.98]"
    assert first[1] == "" and first[2] == "Chapter"

    state.pages[sources[0].key].page, state.pages[sources[1].key].page = 2, 1
    write_outputs(tmp_path, state, sources, Settings())
    names = sorted(p.name for p in (tmp_path / "pages").glob("*.txt"))
    assert names == ["page_001_IMG_0043.txt", "page_002_IMG_0042.txt"]

    text = (tmp_path / "document.txt").read_text(encoding="utf-8")
    assert text.startswith("Test\n") and text.count("--- page ") == 2
    assert text.index("--- page 1 (IMG_0043.jpg) ---") < text.index("--- page 2 (IMG_0042.jpg) ---")


def test_corrections_reach_every_output(tmp_path, make_record):
    sources, state = _job(tmp_path, make_record, ["a.jpg", "b.jpg"])
    rec = state.pages[sources[0].key]
    c = Corrections()
    c.set("p1", 1, "Body of a.jpg, corrected", rec.lines[1]["text"])
    write_outputs(tmp_path, state, sources, Settings(), corrections=c)

    page = (tmp_path / "pages" / "page_001_a.txt").read_text(encoding="utf-8")
    assert (
        page.splitlines()[0].endswith("· 1 line corrected]") and "Body of a.jpg, corrected" in page
    )
    md = (tmp_path / "document.md").read_text(encoding="utf-8")
    assert "Body of a.jpg, corrected" in md and "1 line corrected" in md and "# Chapter" in md
    rows = [
        json.loads(line)
        for line in (tmp_path / "document.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    corrected = [r for r in rows if r["corrected"]]
    assert len(corrected) == 1
    assert corrected[0]["text"] == "Body of a.jpg"  # raw OCR stays
    assert corrected[0]["corrected_line"] == "Body of a.jpg, corrected"
    assert all(r["page_id"] in ("p1", "p2") for r in rows)
    head, row1 = (tmp_path / "report.csv").read_text(encoding="utf-8").splitlines()[:2]
    assert head.split(",") == REPORT_COLUMNS
    assert row1.split(",")[REPORT_COLUMNS.index("corrected_lines")] == "1"


def test_quality_notes_follow_the_provenance_line(tmp_path, make_record):
    sources, state = _job(tmp_path, make_record, ["a.jpg"])
    rec = state.pages[sources[0].key]
    rec.blurry, rec.sharpness = True, 52.0
    write_outputs(tmp_path, state, sources, Settings())
    lines = (tmp_path / "pages" / "page_001_a.txt").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("[page 1 of 1") and lines[1].startswith("[The photo looks blurry")
    assert lines[2] == ""


def test_names_and_provenance_for_pdf_and_error_pages(make_record):
    assert page_file_name(make_record(page=3, label="scan.pdf#p2"), 12) == "page_003_scan_p2.txt"
    err = make_record(page=4, status="error", error="x")
    assert provenance(err, 12) == "[page 4 of 12 · IMG_0001.jpg · could not be read]"
    rot = make_record(page=5, rotation=90, printed_page=11)
    assert provenance(rot, 12, corrected=2) == (
        "[page 5 of 12 · IMG_0001.jpg · read quality 0.98 · rotated 90° · printed page 11"
        " · 2 lines corrected]"
    )
