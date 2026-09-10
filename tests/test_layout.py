import pytest

from usefultext.layout import (
    group_lines,
    layout_page,
    mark_headings,
    mark_paragraphs,
    render_markdown,
    render_text,
    tall_area_fraction,
)
from usefultext.ocr import OcrPageResult, OcrRegion


def box(x, y, w, h, text, conf=0.95):
    return OcrRegion(text, conf, [[x, y], [x + w, y], [x + w, y + h], [x, y + h]])


def test_reading_order_top_to_bottom_then_left_to_right():
    regions = [
        box(300, 100, 100, 20, "right-of-first"),
        box(10, 200, 200, 20, "second line"),
        box(10, 104, 250, 20, "first line"),  # slightly lower centre, same band
        box(10, 300, 200, 20, "third line"),
    ]
    lines = group_lines(regions, band_factor=0.6)
    assert [ln.text for ln in lines] == ["first line right-of-first", "second line", "third line"]


def test_heading_needs_height_and_short_text():
    regions = [box(10, 10, 250, 40, "Chapter One")]
    regions += [box(10, 100 + i * 30, 400, 20, f"body line {i} " * 3) for i in range(6)]
    regions += [box(10, 400, 400, 40, "a tall line but far too long to be a heading " * 3)]
    lines = layout_page(regions)
    assert lines[0].heading is True
    assert all(not ln.heading for ln in lines[1:])


def test_no_heading_on_tiny_page():
    lines = group_lines([box(0, 0, 100, 40, "Big"), box(0, 100, 100, 10, "small")])
    mark_headings(lines)
    assert not any(ln.heading for ln in lines)


def test_paragraph_break_on_large_gap():
    regions = [box(10, i * 30, 300, 20, f"l{i}") for i in range(5)]
    regions.append(box(10, 5 * 30 + 60, 300, 20, "after gap"))
    lines = group_lines(regions)
    mark_paragraphs(lines, gap_factor=1.6)
    text = render_text(lines)
    assert "\n\nafter gap" in text
    assert text.count("\n\n") == 1


def test_markdown_heading_marker():
    lines = group_lines(
        [box(0, 0, 100, 40, "Title")] + [box(0, 100 + i * 30, 300, 20, "body") for i in range(4)]
    )
    mark_headings(lines)
    md = render_markdown(lines, heading_level=2)
    assert md.startswith("## Title")


def test_tall_fraction_flags_sideways_page():
    upright = [box(0, i * 30, 300, 20, "x") for i in range(5)]
    sideways = [box(i * 30, 0, 20, 300, "x") for i in range(5)]
    assert tall_area_fraction(upright) == 0.0
    assert tall_area_fraction(sideways) == 1.0


def test_page_result_gate_and_score():
    r = OcrPageResult(text="", mean_conf=0.6, n_regions=10)
    assert r.low_confidence is True
    assert r.score == 6.0
    assert OcrPageResult("", 0.0, 0).low_confidence is False  # caller decides on blank pages


def test_geometry_is_independent_of_corner_order():
    # A vertical text line (sideways page) as RapidOCR returns it for tilted
    # boxes: the first edge is the long one.
    flipped = OcrRegion("x", 0.9, [[293, 152], [363, 1016], [293, 1021], [223, 158]])
    assert flipped.height > 800 and flipped.width < 100
    normal = box(10, 10, 800, 40, "x")
    assert normal.width == 800 and normal.height == 40
    assert tall_area_fraction([flipped]) == 1.0


def test_curled_heading_halves_join_one_line():
    # Right half lifted 30px by page curl (tolerance would be ~29px). The
    # heading is only 1.15× body height but centred → still a heading.
    left = box(301, 182, 237, 56, "Our Iceberg")
    right = box(522, 150, 333, 60, "Will Never Melt")
    body = [box(190, 300 + i * 52, 770, 52, f"body {i} " * 5) for i in range(8)]
    body.append(box(190, 300 + 8 * 52, 400, 52, "short last line of a paragraph."))
    body.append(box(190, 300 + 9 * 52, 400, 52, "short left-aligned line no period"))
    lines = layout_page([right, left] + body)
    assert lines[0].text == "Our Iceberg Will Never Melt"
    assert lines[0].heading is True
    assert not any(ln.heading for ln in lines[1:])


def test_left_aligned_tall_short_line_is_a_heading():
    head = box(190, 100, 400, 70, "Chapter Two")
    body = [box(190, 220 + i * 52, 770, 48, f"body {i} " * 5) for i in range(8)]
    lines = layout_page([head] + body)
    assert lines[0].heading is True


def test_full_width_tall_line_is_not_a_heading():
    first = box(190, 100, 795, 75, "Two hundred sixty-eight penguins lived in the")
    body = [box(190, 200 + i * 60, 800, 58, f"body {i} " * 5) for i in range(8)]
    lines = layout_page([first] + body)
    assert not any(ln.heading for ln in lines)


def test_clipped_regions_at_photo_edge():
    from usefultext.layout import clipped_at_edge

    body = [box(190, 100 + i * 52, 770, 48, "body") for i in range(6)]
    sliver = [box(1082, 230 + i * 41, 117, 42, "Where tl") for i in range(4)]
    page_number = box(1000, 1500, 30, 40, "7")  # not at the edge
    regions = body + sliver + [page_number]
    idx = clipped_at_edge(regions, image_width=1200)
    assert idx == set(range(6, 10))


# --------------------------------------------------------------------------- #
# Columns
# --------------------------------------------------------------------------- #
def two_column_page(headline=True, rows=12, split_at=None):
    """Two ragged-right columns of `rows` lines (28 px tall, 40 px pitch), a
    headline across both, and optionally a full-width heading between row
    `split_at - 1` and row `split_at`."""
    regions = []
    if headline:
        regions.append(box(100, 150, 800, 70, "A Headline Over Both Columns"))
    for i in range(rows):
        y = 300 + i * 40 + (80 if split_at is not None and i >= split_at else 0)
        regions.append(box(100, y, 380 - (i % 3) * 40, 28, f"left {i}"))
        regions.append(box(560, y, 380 - (i % 4) * 30, 28, f"right {i}"))
    if split_at is not None:
        regions.append(box(100, 300 + split_at * 40 + 5, 800, 40, "Section Two"))
    return regions


def test_two_columns_read_left_then_right():
    from usefultext.layout import column_count, find_gutters

    regions = two_column_page()
    assert len(find_gutters(regions)) == 1
    lines = layout_page(regions)
    texts = [ln.text for ln in lines]
    assert texts[0] == "A Headline Over Both Columns"
    assert lines[0].heading and lines[0].column == 0
    assert texts[1:13] == [f"left {i}" for i in range(12)]
    assert texts[13:] == [f"right {i}" for i in range(12)]
    assert {ln.column for ln in lines[1:13]} == {1}
    assert {ln.column for ln in lines[13:]} == {2}
    # A break after the headline, none between the columns (prose flows across).
    assert lines[1].para_break_before and not lines[13].para_break_before
    assert column_count(lines) == 2


def test_columns_setting_1_keeps_one_column():
    from usefultext.layout import column_count

    lines = layout_page(two_column_page(), columns="1")
    assert lines[1].text == "left 0 right 0"
    assert column_count(lines) == 1


def test_full_width_heading_mid_page_reads_columns_above_it_first():
    lines = layout_page(two_column_page(headline=False, rows=12, split_at=6))
    texts = [ln.text for ln in lines]
    expected = (
        [f"left {i}" for i in range(6)]
        + [f"right {i}" for i in range(6)]
        + ["Section Two"]
        + [f"left {i}" for i in range(6, 12)]
        + [f"right {i}" for i in range(6, 12)]
    )
    assert texts == expected
    heading = lines[12]
    assert heading.heading and heading.column == 0 and heading.para_break_before
    assert lines[13].para_break_before  # the band after the heading
    assert not lines[6].para_break_before  # right column of the same band


def test_short_lines_in_one_column_are_not_columns():
    from usefultext.layout import column_count, find_gutters

    # Dialogue: lines of many widths, all starting at the left margin.
    regions = [box(100, 100 + i * 40, 200 + (i * 137) % 600, 28, f"line {i}") for i in range(20)]
    assert find_gutters(regions) == []
    lines = layout_page(regions)
    assert [ln.text for ln in lines] == [f"line {i}" for i in range(20)]
    assert column_count(lines) == 1


def test_page_numbers_beside_a_contents_list_are_not_a_column():
    from usefultext.layout import find_gutters

    titles = [box(100, 100 + i * 40, 500, 28, f"Chapter {i}") for i in range(8)]
    numbers = [box(800, 100 + i * 40, 30, 28, str(3 + i * 7)) for i in range(8)]
    regions = titles + numbers
    assert find_gutters(regions) == []
    lines = layout_page(regions)
    assert lines[0].text == "Chapter 0 3"


def test_a_few_right_aligned_lines_are_not_a_column():
    from usefultext.layout import find_gutters

    body = [box(100, 100 + i * 40, 600, 28, f"body {i}") for i in range(10)]
    attribution = [box(560, 520 + i * 40, 240, 28, f"— Author {i}") for i in range(2)]
    assert find_gutters(body + attribution) == []


def test_two_columns_on_a_born_digital_pdf(tmp_path):
    """The real engine on a rendered two-column page: read left column, then right."""
    pymupdf = pytest.importorskip("pymupdf")
    from usefultext import ocr
    from usefultext.inputs import PageSource
    from usefultext.pipeline import process_page
    from usefultext.settings import Settings

    if not ocr.available():
        pytest.skip(f"OCR engine unavailable: {ocr.import_error()}")
    left = " ".join(f"alpha{i} lorem ipsum dolor sit amet" for i in range(14))
    right = " ".join(f"beta{i} consectetur adipiscing elit sed" for i in range(14))
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_textbox(pymupdf.Rect(60, 60, 535, 110), "Two Columns", fontsize=24, fontname="hebo")
    page.insert_textbox(pymupdf.Rect(60, 130, 285, 800), left, fontsize=11, fontname="helv")
    page.insert_textbox(pymupdf.Rect(310, 130, 535, 800), right, fontsize=11, fontname="helv")
    path = tmp_path / "two_columns.pdf"
    pdf.save(path)
    pdf.close()

    rec = process_page(PageSource(path, 0), Settings())
    assert rec.status == "done" and rec.columns == 2
    texts = [ln["text"] for ln in rec.lines]
    assert texts[0].lower().startswith("two columns") and rec.lines[0]["heading"]
    alphas = [i for i, t in enumerate(texts) if "alpha" in t]
    betas = [i for i, t in enumerate(texts) if "beta" in t]
    assert alphas and betas and max(alphas) < min(betas)
    assert not any("alpha" in t and "beta" in t for t in texts)
