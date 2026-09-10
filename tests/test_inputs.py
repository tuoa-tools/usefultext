from pathlib import Path

from PIL import Image

from usefultext.inputs import (
    PageSource,
    discover_files,
    name_looks_unhelpful,
    natural_key,
    order_files,
    slug,
)


def test_natural_sort_order():
    names = ["page_10.jpg", "page_9.jpg", "page_1.jpg", "img2.jpg", "img10.jpg"]
    assert sorted(names, key=natural_key) == [
        "img2.jpg",
        "img10.jpg",
        "page_1.jpg",
        "page_9.jpg",
        "page_10.jpg",
    ]


def test_unhelpful_names():
    assert name_looks_unhelpful("5cd3aa12-0e4e-4687-b014-2e07ca96349e")
    assert name_looks_unhelpful("scan")
    assert not name_looks_unhelpful("IMG_20240101_123456")
    assert not name_looks_unhelpful("page_07")


def test_auto_mode_picks_time_for_uuid_names(tmp_path: Path):
    files = []
    for name in ["b" * 8 + "-1111", "a" * 8 + "-2222"]:
        p = tmp_path / f"{name}.png"
        Image.new("RGB", (8, 8)).save(p)
        files.append(p)
    import os
    import time

    os.utime(files[0], (time.time() - 100, time.time() - 100))  # b… is older → first
    ordered, mode = order_files(files, "auto")
    assert mode == "time"
    assert [f.name[0] for f in ordered] == ["b", "a"]
    ordered, mode = order_files(files, "name")
    assert mode == "name" and [f.name[0] for f in ordered] == ["a", "b"]


def test_discover_filters_and_skips_hidden(tmp_path: Path):
    (tmp_path / "a.JPG").write_bytes(b"")
    (tmp_path / "._a.JPG").write_bytes(b"")
    (tmp_path / "notes.txt").write_bytes(b"")
    (tmp_path / "doc.pdf").write_bytes(b"")
    found = {p.name for p in discover_files([tmp_path])}
    assert found == {"a.JPG", "doc.pdf"}


def test_relative_keys_survive_a_move(tmp_path):
    a, b = tmp_path / "a" / "photos", tmp_path / "b" / "photos"
    for d in (a, b):
        d.mkdir(parents=True)
        (d / "x.jpg").write_bytes(b"")
    ka = PageSource(a / "x.jpg", base=tmp_path / "a").key
    kb = PageSource(b / "x.jpg", base=tmp_path / "b").key
    assert ka == kb == "photos/x.jpg::0"
    assert PageSource(a / "x.jpg").key != PageSource(b / "x.jpg").key  # absolute by default


def test_slug_and_page_id():
    assert slug("IMG_0042.jpg") == "IMG_0042"
    assert slug("scan.pdf#p2") == "scan_p2"
    assert slug("my photo (1).HEIC") == "my_photo_1"
    assert slug("x" * 60 + ".jpg") == "x" * 40
    assert PageSource(Path("photos/IMG_0042.jpg")).page_id == "IMG_0042"
    assert PageSource(Path("photos/IMG_0042.jpg"), id="p7").page_id == "p7"
