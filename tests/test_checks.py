from usefultext.checks import (
    find_duplicates,
    job_warnings,
    printed_number_warnings,
    quality_note,
    retake_warnings,
)


def body(n=12):
    return [
        (f"Line {i} of the page about icebergs melting slowly {i * 7}", 200 + i * 60)
        for i in range(n)
    ]


def test_duplicate_pages(make_record):
    a = make_record(page=1, label="a.jpg", lines=body())
    b = make_record(page=2, label="b.jpg", lines=body())
    b.lines[3]["text"] = "Line 3 of the page about icebergs me1ting slowly 21"  # one misread
    other = [(f"Completely different text {i} about penguins", 200 + i * 60) for i in range(12)]
    c = make_record(page=3, label="c.jpg", lines=other)
    w = find_duplicates([a, b, c])
    assert len(w) == 1 and w[0].kind == "duplicate" and w[0].pages == [1, 2]
    assert "a.jpg" in w[0].message and "b.jpg" in w[0].message


def test_printed_numbers(make_record):
    recs = [
        make_record(page=1, printed_page=6),
        make_record(page=2, printed_page=7),
        make_record(page=3, label="x.jpg"),
        make_record(page=4, label="d.jpg", printed_page=9),
        make_record(page=5, label="e.jpg", printed_page=9),
    ]
    w = printed_number_warnings(recs)
    assert {x.kind for x in w} == {"printed_gap", "printed_duplicate"}
    gap = next(x for x in w if x.kind == "printed_gap")
    assert "8" in gap.message and "x.jpg" in gap.message and gap.pages == [3]
    dup = next(x for x in w if x.kind == "printed_duplicate")
    assert dup.pages == [4, 5] and "d.jpg" in dup.message
    assert printed_number_warnings([make_record(page=1)]) == []


def test_gap_with_no_candidate(make_record):
    w = printed_number_warnings(
        [make_record(page=1, printed_page=6), make_record(page=2, printed_page=8)]
    )
    assert len(w) == 1 and w[0].pages == [] and "missing" in w[0].message


def test_retakes(make_record):
    text = [("Some text on the page.", 300)]
    ok = make_record(page=1, lines=text)
    blurry = make_record(page=2, label="IMG_0002.JPG", lines=text, blurry=True, sharpness=52.0)
    low = make_record(page=3, lines=text, mean_conf=0.6, low_conf=True)
    err = make_record(page=4, status="error", error="boom")
    assert retake_warnings([make_record(page=5)])[0].message.endswith("was found on this page.")
    w = retake_warnings([ok, blurry, low, err])
    assert [x.pages for x in w] == [[2], [3], [4]]
    assert all(x.kind == "retake" for x in w)
    assert w[0].message.startswith("Page 2 (IMG_0002.JPG): ")  # the name keeps its case
    assert "blurry" in w[0].message and "read quality" in w[1].message.lower()
    assert "boom" in w[2].message
    assert quality_note(ok) == []
    assert len(job_warnings([ok, blurry, low, err])) == 3
