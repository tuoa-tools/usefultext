from usefultext.corrections import CORRECTIONS_FILE, Corrections, overlay


def test_overlay_without_corrections_is_the_ocr_text(make_record):
    rec = make_record(
        lines=[
            ("Chapter One", 200, True),
            ("The iceberg was melting.", 300),
            ("Nobody noticed.", 360),
        ]
    )
    lines = overlay(rec)
    assert [ln.text for ln in lines] == [
        "Chapter One",
        "The iceberg was melting.",
        "Nobody noticed.",
    ]
    assert lines[0].heading and all(ln.origin == "ocr" for ln in lines)
    assert [ln.index for ln in lines] == [0, 1, 2]


def test_furniture_is_skipped_unless_asked(make_record):
    rec = make_record(lines=[("OUR ICEBERG | 7", 60), ("Body text here.", 300)])
    rec.lines[0]["furniture"] = True
    assert [ln.text for ln in overlay(rec)] == ["Body text here."]
    assert len(overlay(rec, skip_furniture=False)) == 2


def test_set_revert_and_counts(make_record):
    rec = make_record(id="p1", lines=[("The iceberg was me1ting.", 300), ("Nobody noticed.", 360)])
    c = Corrections()
    c.set("p1", 0, "The iceberg was melting.", rec.lines[0]["text"])
    assert c.count(rec) == 1 and c.total() == 1
    lines = overlay(rec, corrections=c)
    assert lines[0].text == "The iceberg was melting."
    assert lines[0].origin == "human" and lines[0].index == 0
    assert lines[1].origin == "ocr"
    assert c.revert("p1", 0) is True
    assert c.count(rec) == 0 and c.revert("p1", 0) is False
    assert c.pages == {}


def test_newlines_add_lines_and_empty_drops(make_record):
    rec = make_record(id="p1", lines=[("first", 300, True), ("second", 360), ("third", 420)])
    rec.lines[1]["para_break_before"] = True
    c = Corrections()
    c.set("p1", 0, "first\nfirst and a half", "first")
    c.set("p1", 1, "", "second")
    lines = overlay(rec, corrections=c)
    assert [ln.text for ln in lines] == ["first", "first and a half", "third"]
    assert [ln.heading for ln in lines] == [True, False, False]  # only the first piece
    assert [ln.index for ln in lines] == [0, 0, 2]


def test_stale_after_a_reread(make_record):
    rec = make_record(id="p1", lines=[("old reading", 300)])
    c = Corrections()
    c.set("p1", 0, "fixed", "old reading")
    rec.lines[0]["text"] = "new reading"  # the page was read again
    assert c.count(rec) == 0
    assert [(i, corr.text) for i, corr in c.stale(rec)] == [(0, "fixed")]
    assert overlay(rec, corrections=c)[0].text == "new reading"
    c.set("p1", 5, "beyond the end", "x")
    assert [i for i, _ in c.stale(rec)] == [0, 5]


def test_roundtrip_and_missing_file(tmp_path):
    c = Corrections()
    c.set("p1", 2, "fixed", "orig")
    c.save(tmp_path)
    loaded = Corrections.load(tmp_path)
    page = loaded.for_page("p1")
    assert page[2].text == "fixed" and page[2].ocr == "orig" and page[2].at
    assert (tmp_path / CORRECTIONS_FILE).exists()
    assert Corrections.load(tmp_path / "nowhere").total() == 0
    (tmp_path / CORRECTIONS_FILE).write_text("{not json", encoding="utf-8")
    assert Corrections.load(tmp_path).total() == 0  # corrupt file never blocks a run


def test_stripped_column_top_line_hands_its_break_to_the_next_line(make_record):
    # A spread read as two columns: "28" tops the left column, "29" the right.
    # The gap under each number gave the next line a paragraph break; once the
    # numbers are stripped, the right column must still follow the left one
    # without a blank line (prose flows across the gutter).
    rec = make_record(
        lines=[("28", 100), ("left one", 300), ("left two", 340), ("29", 100), ("right one", 300)]
    )
    for i, ln in enumerate(rec.lines):
        ln["column"] = 1 if i < 3 else 2
    rec.lines[0]["furniture"] = rec.lines[3]["furniture"] = True
    rec.lines[1]["para_break_before"] = rec.lines[4]["para_break_before"] = True
    assert rec.body_text() == "left one\nleft two\nright one"
    # A stripped line that starts a new band (full width) passes its own break on.
    rec.lines[3]["column"] = 0
    rec.lines[3]["para_break_before"] = True
    rec.lines[4]["column"] = 0
    rec.lines[4]["para_break_before"] = False
    assert rec.body_text() == "left one\nleft two\n\nright one"
