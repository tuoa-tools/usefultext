from phototext.ocr import OcrRegion, OcrPageResult
from phototext.layout import (group_lines, mark_headings, mark_paragraphs, render_text,
                              render_markdown, tall_area_fraction, layout_page)


def box(x, y, w, h, text, conf=0.95):
    return OcrRegion(text, conf, [[x, y], [x + w, y], [x + w, y + h], [x, y + h]])


def test_reading_order_top_to_bottom_then_left_to_right():
    regions = [
        box(300, 100, 100, 20, "right-of-first"),
        box(10, 200, 200, 20, "second line"),
        box(10, 104, 250, 20, "first line"),     # slightly lower centre, same band
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
    lines = group_lines([box(0, 0, 100, 40, "Title")] + [box(0, 100 + i * 30, 300, 20, "body") for i in range(4)])
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
    assert OcrPageResult("", 0.0, 0).low_confidence is False   # caller decides on blank pages


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
    from phototext.layout import clipped_at_edge
    body = [box(190, 100 + i * 52, 770, 48, "body") for i in range(6)]
    sliver = [box(1082, 230 + i * 41, 117, 42, "Where tl") for i in range(4)]
    page_number = box(1000, 1500, 30, 40, "7")           # not at the edge
    regions = body + sliver + [page_number]
    idx = clipped_at_edge(regions, image_width=1200)
    assert idx == set(range(6, 10))
