from pathlib import Path

from PIL import Image

from usefultext.inputs import discover_files, name_looks_unhelpful, natural_key, order_files


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
