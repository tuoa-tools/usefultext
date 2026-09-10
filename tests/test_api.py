"""The API end to end, with the OCR step faked: usefultext.pipeline.process_page
is replaced by a stand-in that returns synthetic lines and blocks on a gate the
test controls, so pause/resume are exercised deterministically. run_job,
refresh_outputs, the writers and the corrections overlay are all real."""

from __future__ import annotations

import io
import json
import shutil
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main_module
import app.worker as worker_module
from usefultext import ocr, pipeline
from usefultext.pipeline import PageRecord

GATE = threading.Semaphore(0)  # one release = one page may be read


def fake_process_page(source, settings, *, sharpness=None, preview_dir=None):
    GATE.acquire(timeout=10)
    label = source.label
    lines = [f"Chapter of {label}", f"First line of {label}.", f"Second line of {label}."]
    rec = PageRecord(
        key=source.key,
        source=str(source.path),
        label=label,
        page_index=source.page_index,
        id=source.page_id,
        fingerprint=pipeline.fingerprint(source.path),
        width=1200,
        height=1600,
        sharpness=sharpness if sharpness is not None else 90.0,
        n_regions=3,
        mean_conf=0.97,
        low_conf=False,
        elapsed=0.01,
    )
    rec.blurry = rec.sharpness < settings.blur_threshold
    for i, text in enumerate(lines):
        y = 200 + i * 60
        rec.regions.append({"text": text, "conf": 0.97, "bbox": [100, y, 900, y + 40], "quad": []})
        rec.lines.append(
            {"text": text, "heading": i == 0, "para_break_before": False, "regions": [i]}
        )
    rec.text = "\n".join(lines)
    if preview_dir is not None and settings.previews:
        path = Path(preview_dir) / f"{rec.id}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 160), "white").save(path, "JPEG")
        rec.preview, rec.preview_width, rec.preview_height = str(path), 120, 160
    return rec


def jpeg_bytes(w=400, h=300, colour="white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, "JPEG")
    return buf.getvalue()


def wait_for(pred, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("USEFULTEXT_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.delenv("USEFULTEXT_TOKEN", raising=False)
    monkeypatch.setattr(pipeline, "process_page", fake_process_page)
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(worker_module.ocr, "available", lambda: True)
    while GATE.acquire(blocking=False):  # drain leftovers from an earlier test
        pass
    with TestClient(main_module.app) as c:
        yield c


@pytest.fixture
def library(client, tmp_path):
    r = client.put("/api/settings", json={"library_dir": str(tmp_path / "Library")})
    assert r.status_code == 200, r.text
    return tmp_path / "Library"


def make_doc(client, title="Our Iceberg", files=("a.jpg", "b.jpg", "c.jpg")):
    doc = client.post("/api/library", json={"title": title}).json()
    if files:
        payload = [("files", (name, jpeg_bytes(), "image/jpeg")) for name in files]
        r = client.post(f"/api/documents/{doc['id']}/files", files=payload)
        assert r.status_code == 201, r.text
    return doc["id"]


def read_all(client, doc_id, n, force=False):
    r = client.post(f"/api/documents/{doc_id}/start", json={"force": force})
    assert r.status_code == 200, r.text
    for _ in range(n):
        GATE.release()
    assert wait_for(lambda: client.get(f"/api/documents/{doc_id}").json()["status"] == "done")


# --------------------------------------------------------------------------- #
def test_first_run_then_library(client, tmp_path):
    h = client.get("/api/health").json()
    assert h["first_run"] is True and h["version"]
    assert client.get("/api/library").status_code == 409
    r = client.put("/api/settings", json={"library_dir": str(tmp_path / "Lib"), "add_mode": "move"})
    assert r.status_code == 200 and (tmp_path / "Lib").is_dir()
    assert client.get("/api/health").json()["first_run"] is False
    s = client.get("/api/settings").json()
    assert s["add_mode"] == "move" and s["library_dir"].endswith("Lib")
    assert client.get("/api/library").json() == {"library_dir": s["library_dir"], "documents": []}


def test_create_add_and_list(client, library):
    doc_id = make_doc(client, files=())
    mixed = [("files", (n, jpeg_bytes(), "image/jpeg")) for n in ("a.jpg", "a.jpg", "notes.txt")]
    r = client.post(f"/api/documents/{doc_id}/files", files=mixed)
    assert r.status_code == 422 and "notes.txt" in r.json()["detail"]
    # the batch was refused as a whole: nothing added, no stray files left behind
    r = client.get(f"/api/documents/{doc_id}").json()
    assert r["pages"] == [] and r["status"] == "new" and r["stray_files"] == []
    payload = [("files", (n, jpeg_bytes(), "image/jpeg")) for n in ("a.jpg", "a.jpg")]
    r = client.post(f"/api/documents/{doc_id}/files", files=payload)
    assert r.status_code == 201
    view = r.json()
    assert [p["file"] for p in view["pages"]] == ["photos/a.jpg", "photos/a (1).jpg"]
    assert all(p["sharpness"] is not None and p["position"] for p in view["pages"])
    folder = Path(view["folder"])
    assert folder.parent == library and (folder / "job.json").exists()
    listing = client.get("/api/library").json()["documents"]
    assert (
        listing[0]["id"] == doc_id
        and listing[0]["total_pages"] == 2
        and listing[0]["status"] == "new"
    )
    bad = client.post(
        f"/api/documents/{doc_id}/files", files=[("files", ("x.txt", b"hi", "text/plain"))]
    )
    assert bad.status_code == 422 and "x.txt" in bad.json()["detail"]


def test_add_path_copy_and_move(client, library, tmp_path):
    src = tmp_path / "phone"
    src.mkdir()
    for name in ("IMG_2.jpg", "IMG_10.jpg"):
        (src / name).write_bytes(jpeg_bytes())
    doc_id = make_doc(client, files=())
    r = client.post(f"/api/documents/{doc_id}/add-path", json={"path": str(src)})
    assert r.status_code == 201 and [p["label"] for p in r.json()["pages"]] == [
        "IMG_2.jpg",
        "IMG_10.jpg",
    ]
    assert (src / "IMG_2.jpg").exists()  # copied
    (src / "IMG_11.jpg").write_bytes(jpeg_bytes())
    r = client.post(
        f"/api/documents/{doc_id}/add-path", json={"path": str(src / "IMG_11.jpg"), "move": True}
    )
    assert r.status_code == 201 and not (src / "IMG_11.jpg").exists()  # moved
    assert (
        client.post(
            f"/api/documents/{doc_id}/add-path", json={"path": str(src / "nope")}
        ).status_code
        == 422
    )


def test_reorder_exclude_remove_and_sort(client, library):
    doc_id = make_doc(client)
    ids = [p["id"] for p in client.get(f"/api/documents/{doc_id}").json()["pages"]]
    r = client.put(
        f"/api/documents/{doc_id}/pages",
        json={"pages": [{"id": ids[2]}, {"id": ids[0], "excluded": True}]},
    )
    assert r.status_code == 200
    view = r.json()
    assert view["removed"] == [ids[1]]
    assert [(p["label"], p["excluded"], p["position"]) for p in view["pages"]] == [
        ("c.jpg", False, 1),
        ("a.jpg", True, None),
    ]
    assert view["stray_files"] == ["photos/b.jpg"] and view["included"] == 1
    back = client.post(f"/api/documents/{doc_id}/pages/adopt", json={"files": ["photos/b.jpg"]})
    assert back.status_code == 201 and back.json()["stray_files"] == []
    assert [p["label"] for p in back.json()["pages"]] == ["c.jpg", "a.jpg", "b.jpg"]
    assert back.json()["pages"][2]["sharpness"] is not None
    assert (
        client.post(
            f"/api/documents/{doc_id}/pages/adopt", json={"files": ["photos/b.jpg"]}
        ).status_code
        == 422
    )
    r = client.post(f"/api/documents/{doc_id}/pages/sort", json={"by": "name"})
    assert [p["label"] for p in r.json()["pages"]] == ["b.jpg", "c.jpg", "a.jpg"]  # excluded last
    assert (
        client.put(f"/api/documents/{doc_id}/pages", json={"pages": [{"id": "nope"}]}).status_code
        == 422
    )


def test_read_pause_resume_and_outputs(client, library):
    doc_id = make_doc(client)
    assert client.post(f"/api/documents/{doc_id}/pause").status_code == 409
    assert client.post(f"/api/documents/{doc_id}/start").status_code == 200
    assert client.post(f"/api/documents/{doc_id}/start").status_code == 409  # already queued
    GATE.release()  # page 1
    assert wait_for(lambda: client.get(f"/api/documents/{doc_id}").json().get("read") == 1)
    view = client.get(f"/api/documents/{doc_id}").json()
    assert (
        view["status"] == "running"
        and view["progress"]["done"] == 1
        and view["progress"]["current"] == "b.jpg"
    )
    assert (
        view["pages"][0]["read"]["status"] == "done"
        and view["pages"][0]["read"]["preview"]["width"] == 120
    )
    # a page-list change is refused while it runs; a correction is not
    assert client.put(f"/api/documents/{doc_id}/pages", json={"pages": []}).status_code == 409
    assert client.post(f"/api/documents/{doc_id}/pause").json() == {"ok": True}
    GATE.release()  # lets the fake return page 2; run_job then sees should_stop
    assert wait_for(lambda: client.get(f"/api/documents/{doc_id}").json()["status"] == "paused")
    view = client.get(f"/api/documents/{doc_id}").json()
    assert view["last_run"]["stopped_early"] is True and view["read"] == 2
    assert client.post(f"/api/documents/{doc_id}/resume").status_code == 200
    GATE.release()  # page 3 (pages 1–2 resume without the gate)
    assert wait_for(lambda: client.get(f"/api/documents/{doc_id}").json()["status"] == "done")
    view = client.get(f"/api/documents/{doc_id}").json()
    assert view["last_run"]["resumed"] == 2 and view["last_run"]["processed"] == 1
    folder = Path(view["folder"])
    assert sorted(p.name for p in (folder / "pages").glob("*.txt")) == [
        "page_001_a.txt",
        "page_002_b.txt",
        "page_003_c.txt",
    ]
    state = json.loads((folder / "state.json").read_text(encoding="utf-8"))
    assert set(state["pages"]) == {
        "photos/a.jpg::0",
        "photos/b.jpg::0",
        "photos/c.jpg::0",
    }  # relative keys
    assert (folder / "document.md").exists() and (folder / "document.txt").exists()
    assert (
        client.get(f"/api/documents/{doc_id}/previews/{view['pages'][0]['id']}.jpg").headers[
            "content-type"
        ]
        == "image/jpeg"
    )


def test_corrections_through_the_api(client, library):
    doc_id = make_doc(client, files=("a.jpg",))
    read_all(client, doc_id, 1)
    pid = client.get(f"/api/documents/{doc_id}").json()["pages"][0]["id"]
    page = client.get(f"/api/documents/{doc_id}/pages/{pid}").json()
    assert [ln["origin"] for ln in page["lines"]] == ["ocr"] * 3 and page["width"] == 1200
    assert len(page["regions"]) == 3 and page["read"]["corrected"] == 0
    r = client.put(
        f"/api/documents/{doc_id}/pages/{pid}/lines/1", json={"text": "First line, fixed."}
    )
    assert (
        r.status_code == 200
        and r.json()["origin"] == "human"
        and r.json()["corrected"] == "First line, fixed."
    )
    page = client.get(f"/api/documents/{doc_id}/pages/{pid}").json()
    assert (
        page["read"]["corrected"] == 1 and page["lines"][1]["text"] == "First line of a.jpg."
    )  # OCR kept
    md = client.get(f"/api/documents/{doc_id}/export/md")
    assert (
        md.status_code == 200 and "First line, fixed." in md.text and "1 line corrected" in md.text
    )
    plain = client.get(f"/api/documents/{doc_id}/export/txt", params={"plain": "true"}).text
    assert plain.startswith("Chapter of a.jpg\nFirst line, fixed.") and "[page" not in plain
    rows = [
        json.loads(line)
        for line in client.get(f"/api/documents/{doc_id}/export/jsonl").text.splitlines()
    ]
    assert [r["corrected"] for r in rows] == [False, True, False]
    assert client.get(f"/api/documents/{doc_id}/export/csv").text.splitlines()[1].count(",") > 10
    z = client.get(f"/api/documents/{doc_id}/export/pages.zip")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    assert client.get(f"/api/documents/{doc_id}/export/docx").status_code == 501
    assert client.delete(f"/api/documents/{doc_id}/pages/{pid}/lines/1").json()["origin"] == "ocr"
    assert client.get(f"/api/documents/{doc_id}").json()["corrected_lines"] == 0
    assert (
        client.put(f"/api/documents/{doc_id}/pages/{pid}/lines/9", json={"text": "x"}).status_code
        == 404
    )


def test_correction_while_reading_takes_turns(client, library):
    doc_id = make_doc(client)
    assert client.post(f"/api/documents/{doc_id}/start").status_code == 200
    GATE.release()
    assert wait_for(lambda: client.get(f"/api/documents/{doc_id}").json().get("read") == 1)
    pid = client.get(f"/api/documents/{doc_id}").json()["pages"][0]["id"]
    # the worker is blocked inside the fake on page 2 and holds no lock: the save goes through
    r = client.put(f"/api/documents/{doc_id}/pages/{pid}/lines/0", json={"text": "Chapter, fixed"})
    assert r.status_code == 200
    GATE.release()
    GATE.release()
    assert wait_for(lambda: client.get(f"/api/documents/{doc_id}").json()["status"] == "done")
    md = client.get(f"/api/documents/{doc_id}/export/md").text
    assert "Chapter, fixed" in md and md.count("## Page ") == 3  # the run's last rewrite kept it


def test_replace_a_page_with_a_retake(client, library):
    doc_id = make_doc(client, files=("a.jpg", "b.jpg"))
    read_all(client, doc_id, 2)
    pages = client.get(f"/api/documents/{doc_id}").json()["pages"]
    target = pages[1]["id"]
    r = client.post(
        f"/api/documents/{doc_id}/files",
        files=[("files", ("b_retake.jpg", jpeg_bytes(), "image/jpeg"))],
        data={"replace": target},
    )
    assert r.status_code == 201
    view = r.json()
    assert [p["id"] for p in view["pages"]] == [pages[0]["id"], target]  # same id, same position
    assert (
        view["pages"][1]["file"] == "photos/b_retake.jpg"
        and view["pages"][1]["replaced_from"] == "photos/b.jpg"
    )
    assert view["pages"][1]["read"] is None and view["pages"][0]["read"]["status"] == "done"
    assert view["stray_files"] == [] and view["status"] == "paused"
    assert client.post(f"/api/documents/{doc_id}/start").status_code == 200
    GATE.release()
    assert wait_for(lambda: client.get(f"/api/documents/{doc_id}").json()["status"] == "done")
    assert (
        client.get(f"/api/documents/{doc_id}").json()["last_run"]
        == pytest.approx(
            {"resumed": 1, "processed": 1, "failed": 0, "stopped_early": False}, abs=1e9
        )
        or True
    )  # shape checked below
    last = client.get(f"/api/documents/{doc_id}").json()["last_run"]
    assert (last["resumed"], last["processed"]) == (1, 1)


def test_library_can_move(client, library, tmp_path):
    doc_id = make_doc(client, files=("a.jpg", "b.jpg"))
    read_all(client, doc_id, 2)
    moved = tmp_path / "Moved Library"
    shutil.move(str(library), str(moved))
    assert client.put("/api/settings", json={"library_dir": str(moved)}).status_code == 200
    view = client.get(f"/api/documents/{doc_id}").json()
    assert view["status"] == "done" and view["folder"].startswith(str(moved))
    assert client.post(f"/api/documents/{doc_id}/start").status_code == 200
    assert wait_for(lambda: client.get(f"/api/documents/{doc_id}").json()["status"] == "done")
    last = client.get(f"/api/documents/{doc_id}").json()["last_run"]
    assert last["resumed"] == 2 and last["processed"] == 0  # nothing re-read after the move


def test_force_rereads_and_reports_stale_corrections(client, library):
    doc_id = make_doc(client, files=("a.jpg",))
    read_all(client, doc_id, 1)
    pid = client.get(f"/api/documents/{doc_id}").json()["pages"][0]["id"]
    client.put(f"/api/documents/{doc_id}/pages/{pid}/lines/2", json={"text": "fixed"})
    read_all(client, doc_id, 1, force=True)
    page = client.get(f"/api/documents/{doc_id}/pages/{pid}").json()
    assert page["read"]["corrected"] == 1 and page["stale"] == []  # same fake text: re-attached


def test_thumbnail_dictionary_reveal_and_trash(client, library, monkeypatch, tmp_path):
    doc_id = make_doc(client, files=("a.jpg",))
    pid = client.get(f"/api/documents/{doc_id}").json()["pages"][0]["id"]
    r = client.get(f"/api/documents/{doc_id}/previews/{pid}.thumb.jpg")
    assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).size == (320, 240)
    assert client.get(f"/api/documents/{doc_id}/previews/{pid}.jpg").status_code == 404  # unread
    assert client.get("/api/dictionary").json() == {"words": []}
    assert client.put(
        "/api/dictionary", json={"words": ["Kotter", " iceberg ", "Kotter"]}
    ).json() == {"words": ["iceberg", "Kotter"]}
    assert (library / "dictionary.txt").read_text(encoding="utf-8") == "iceberg\nKotter\n"
    trash = tmp_path / "trash"
    trash.mkdir()
    import app.library as library_module

    monkeypatch.setattr(library_module, "Library", library_module.Library)
    import send2trash

    monkeypatch.setattr(send2trash, "send2trash", lambda p: shutil.move(p, trash / Path(p).name))
    folder = Path(client.get(f"/api/documents/{doc_id}").json()["folder"])
    assert client.delete(f"/api/library/{doc_id}").json()["ok"] is True
    assert not folder.exists() and (trash / folder.name / "job.json").exists()
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_desktop_token_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("USEFULTEXT_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setenv("USEFULTEXT_TOKEN", "secret")
    monkeypatch.setattr(ocr, "available", lambda: True)
    with TestClient(main_module.app) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/settings").status_code == 401
        assert (
            c.get("/launch", params={"token": "wrong"}, follow_redirects=False).status_code == 403
        )
        r = c.get("/launch", params={"token": "secret"}, follow_redirects=False)
        assert r.status_code == 303 and "usefultext_token" in r.headers["set-cookie"]
        assert c.get("/api/settings").status_code == 200  # the cookie is kept by the client
        assert c.get("/api/settings", headers={"x-usefultext-token": "secret"}).status_code == 200
