import pytest

from usefultext.pipeline import PageRecord


@pytest.fixture
def make_record():
    """A PageRecord factory for tests that need lines without running OCR.

    `lines` are (text, y) or (text, y, heading) tuples, one region per line,
    laid out on a 1200×1600 page. Any other PageRecord field can be set by
    keyword (mean_conf=0.6, low_conf=True, printed_page=9, status="error" ...).
    """

    def _make(page=1, label="IMG_0001.jpg", lines=(), *, key=None, id=None, **fields):
        regions, recs = [], []
        for i, ln in enumerate(lines):
            text, y, heading = (ln[0], ln[1], ln[2] if len(ln) > 2 else False)
            quad = [[100, y - 20], [800, y - 20], [800, y + 20], [100, y + 20]]
            regions.append(
                {"text": text, "conf": 0.99, "quad": quad, "bbox": [100, y - 20, 800, y + 20]}
            )
            recs.append(
                {
                    "text": text,
                    "heading": heading,
                    "para_break_before": False,
                    "regions": [i],
                    "furniture": False,
                }
            )
        base = dict(
            key=key or f"{label}::0",
            source=label,
            label=label,
            id=id or label.split(".")[0],
            page=page,
            status="done",
            width=1200,
            height=1600,
            sharpness=90.0,
            blurry=False,
            n_regions=len(regions),
            mean_conf=0.98,
            low_conf=False,
            lines=recs,
            regions=regions,
        )
        base.update(fields)
        rec = PageRecord(**base)
        rec.text = "\n".join(r["text"] for r in recs)
        return rec

    return _make
