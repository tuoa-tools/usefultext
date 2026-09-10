import os

import pytest

from usefultext import fileio


def test_write_text_swaps_into_place_and_leaves_no_tmp(tmp_path):
    p = tmp_path / "state.json"
    fileio.write_text(p, "one")
    fileio.write_text(p, "two")
    assert p.read_text(encoding="utf-8") == "two"
    assert not fileio.tmp_path(p).exists()
    assert fileio.read_text(p) == "two"
    assert fileio.read_text(tmp_path / "missing.json") is None


def test_replace_retries_while_the_destination_is_held(tmp_path, monkeypatch):
    # Windows refuses the swap while another handle has the file open; the
    # handle is gone a moment later. Two refusals, then it goes through.
    p = tmp_path / "job.json"
    real_replace = os.replace
    calls = []

    def flaky(src, dst):
        calls.append(1)
        if len(calls) <= 2:
            raise PermissionError(13, "Access is denied")
        real_replace(src, dst)

    monkeypatch.setattr(fileio.os, "replace", flaky)
    fileio.write_text(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello" and len(calls) == 3


def test_replace_gives_up_after_the_deadline(tmp_path, monkeypatch):
    def refused(src, dst):
        raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(fileio.os, "replace", refused)
    tmp = tmp_path / "x.tmp"
    tmp.write_text("x", encoding="utf-8")
    with pytest.raises(PermissionError):
        fileio.replace(tmp, tmp_path / "x", retry_seconds=0.05)


def test_read_text_retries_while_the_file_is_being_swapped(tmp_path, monkeypatch):
    p = tmp_path / "corrections.json"
    p.write_text("ok", encoding="utf-8")
    real_read = fileio.Path.read_text
    calls = []

    def flaky(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError(5, "Access is denied")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(fileio.Path, "read_text", flaky)
    assert fileio.read_text(p) == "ok" and len(calls) == 2
