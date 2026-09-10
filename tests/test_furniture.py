from types import SimpleNamespace

from usefultext.furniture import (
    detect_furniture,
    order_by_printed_page,
    printed_number,
    signature,
    similar,
)


def page(lines, height=1600, status="done"):
    """A minimal PageRecord-like object: lines with one region each at a y."""
    regions, out = [], []
    for i, (text, y, heading) in enumerate(lines):
        regions.append({"text": text, "conf": 0.99, "bbox": [100, y - 20, 800, y + 20]})
        out.append({"text": text, "heading": heading, "regions": [i]})
    return SimpleNamespace(
        status=status, height=height, lines=out, regions=regions, furniture=[], printed_page=None
    )


def source(key):
    """A minimal PageSource-like object."""
    return SimpleNamespace(key=key, label=key)


def test_signature_and_similarity():
    assert signature("6 | JOHN KOTTER AND HOLGER RATHGEBER") == "john kotter and holger rathgeber"
    assert similar(
        signature("10 | JOHN KOTTER AND HC"), signature("6 | JOHN KOTTER AND HOLGER RATHGEBER")
    )
    assert not similar("our iceberg is melting", "john kotter and holger rathgeber")


def test_printed_number():
    assert printed_number("6 | JOHN KOTTER AND HOLGER RATHGEBER") == 6
    assert printed_number("OUR ICEBERG IS MELTING | 9") == 9
    assert printed_number("12") == 12
    assert printed_number("Chapter 3 of 12 sections") is None
    assert printed_number("no digits") is None


def test_detects_alternating_footers_but_not_titles():
    body = [(f"body line {i}", 400 + i * 60, False) for i in range(10)]
    p6 = page(
        [("Our Iceberg Will Never Melt", 190, True)]
        + body
        + [("6 | JOHN KOTTER AND HOLGER RATHGEBER", 1540, False)]
    )
    p7 = page(body + [("OUR ICEBERG IS MELTING | 7", 1470, False)])
    p9 = page(body + [("OUR ICEBERG IS MELTING | 9", 1480, False)])
    p10 = page(body + [("10 | JOHN KOTTER AND HC", 1520, False)])
    p8 = page([("A one-off caption line", 120, False)] + body)
    detect_furniture([p6, p7, p8, p9, p10])
    assert [r.printed_page for r in (p6, p7, p8, p9, p10)] == [6, 7, None, 9, 10]
    assert p6.lines[0]["furniture"] is False  # the title survives
    assert p6.lines[-1]["furniture"] is True
    assert p8.lines[0]["furniture"] is False  # appears once → not furniture
    assert all(not ln["furniture"] for ln in p7.lines[:-1])


def test_order_by_printed_page_fills_gaps():
    sources = [source("p8"), source("p6"), source("p7"), source("p10"), source("p9"), source("p11")]
    printed = {"p6": 6, "p7": 7, "p9": 9, "p10": 10}
    ordered, notes = order_by_printed_page(sources, printed)
    assert [s.key for s in ordered] == ["p6", "p7", "p8", "p9", "p10", "p11"]
    assert any("p8" in n and "gap" in n for n in notes)
    assert any("p11" in n and "after" in n for n in notes)


def test_order_by_printed_page_without_numbers_is_unchanged():
    sources = [source("a"), source("b")]
    ordered, notes = order_by_printed_page(sources, {})
    assert [s.key for s in ordered] == ["a", "b"] and notes


def test_page_numbers_at_the_top_of_each_column_of_a_spread():
    # A magazine spread read as two columns: "28" tops the left column and
    # "29" the right one, so each column's own ends are furniture candidates.
    def spread(n):
        left = [(f"left {i}", 300 + i * 60, False) for i in range(8)]
        right = [(f"right {i}", 300 + i * 60, False) for i in range(8)]
        p = page([(str(n), 120, False)] + left + [(str(n + 1), 120, False)] + right)
        for ln in p.lines[:9]:
            ln["column"] = 1
        for ln in p.lines[9:]:
            ln["column"] = 2
        return p

    first, second = spread(28), spread(30)
    detect_furniture([first, second])
    assert first.lines[0]["furniture"] and first.lines[9]["furniture"]
    assert not any(ln["furniture"] for ln in first.lines[1:9])
    assert (first.printed_page, second.printed_page) == (28, 30)
