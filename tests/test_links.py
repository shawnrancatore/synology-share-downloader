# Copyright 2026 Dynamo Foundry LLC
# Licensed under the Apache License, Version 2.0.
"""The app never writes through a link: not the file, not its .part file."""
import os

import pytest
import requests

from synology_share_downloader import client as client_module
from synology_share_downloader.client import SKIPPED, apply_file_times
from synology_share_downloader.plan import UnsafePathError, safe_local_path

OLD = 1_000_000_000  # an mtime far in the past


def _link(target, link):
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("this system does not let us create a symlink")


def _hard_link(target, link):
    try:
        os.link(str(target), str(link))
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("this system does not let us create a hard link")


def _outside_file(outside, content=b"keep"):
    target = outside / "target.txt"
    target.write_bytes(content)
    os.utime(str(target), (OLD, OLD))
    return target


def _untouched(target, content=b"keep"):
    return target.read_bytes() == content and os.stat(str(target)).st_mtime == OLD


def _says_how_to_recover(logs):
    """True if the hard-link skip line is there and ends with the way out."""
    return any(m.startswith("Skipped (hard link) ") and m.endswith("delete the .part file to download it again.")
               for m in logs)


def _no_sleep(monkeypatch):
    def fail(_seconds):
        raise AssertionError("the download waited to retry")
    monkeypatch.setattr(client_module.time, "sleep", fail)


@pytest.fixture
def dirs(tmp_path):
    dest, outside = tmp_path / "dest", tmp_path / "outside"
    dest.mkdir()
    outside.mkdir()
    return dest, outside


def _nas(fake_nas, content=b"data"):
    return fake_nas({"/share": [("a.txt", "/share/a.txt", False)]}, {"/share/a.txt": content})


def _downloads(nas):
    return [c for c in nas.calls if c[2] == "SYNO.FolderSharing.Download"]


def test_safe_local_path_rejects_a_part_file_linked_outside(dirs):
    dest, outside = dirs
    (dest / "share").mkdir()
    _link(outside / "x", dest / "share" / "a.txt.part")
    with pytest.raises(UnsafePathError, match="part"):
        safe_local_path(str(dest), "/share/a.txt", "")


@pytest.mark.parametrize("expected_size", [4, 5])  # 4: the "already complete" branch
def test_a_linked_file_is_refused_and_its_target_left_alone(dirs, fake_nas, connect, expected_size):
    dest, outside = dirs
    target = outside / "target.txt"
    target.write_bytes(b"keep")
    os.utime(str(target), (OLD, OLD))
    _link(target, dest / "a.txt")
    logs = []
    nas = _nas(fake_nas)
    client = connect(nas, log=logs.append)

    ok = client.download_file("/share/a.txt", str(dest / "a.txt"), expected_size, mtime=2_000_000_000)

    assert ok is SKIPPED and not ok
    assert target.read_bytes() == b"keep"
    assert os.stat(str(target)).st_mtime == OLD
    assert os.path.islink(str(dest / "a.txt"))
    assert not (dest / "a.txt.part").exists()
    assert _downloads(nas) == []
    assert any(m.startswith("Skipped ") and "link" in m for m in logs)


def test_a_dangling_part_link_creates_nothing_outside(dirs, fake_nas, connect):
    dest, outside = dirs
    _link(outside / "new.bin", dest / "a.txt.part")
    logs = []
    client = connect(_nas(fake_nas), log=logs.append)

    ok = client.download_file("/share/a.txt", str(dest / "a.txt"), 4)

    assert ok is SKIPPED and not ok
    assert list(outside.iterdir()) == []
    assert not (dest / "a.txt").exists()
    assert any(m.startswith("Skipped ") and "link" in m for m in logs)


def test_a_resumed_file_is_a_regular_file(dirs, fake_nas, connect):
    dest, _ = dirs
    (dest / "a.txt.part").write_bytes(b"da")
    nas = _nas(fake_nas)
    client = connect(nas)

    assert client.download_file("/share/a.txt", str(dest / "a.txt"), 4)

    final = dest / "a.txt"
    assert not os.path.islink(str(final)) and final.read_bytes() == b"data"
    assert not (dest / "a.txt.part").exists()


# ---- symbolic links that are there before, or appear during, a download ----

def test_a_part_link_to_an_existing_outside_file_leaves_it_alone(dirs, fake_nas, connect):
    dest, outside = dirs
    target = _outside_file(outside)
    _link(target, dest / "a.txt.part")
    logs = []
    nas = _nas(fake_nas)

    ok = connect(nas, log=logs.append).download_file("/share/a.txt", str(dest / "a.txt"), 4)

    assert ok is SKIPPED
    assert _untouched(target)
    assert _downloads(nas) == []
    assert any(m.startswith("Skipped (symbolic link) ") for m in logs)


# open() refuses a symbolic link where the OS has O_NOFOLLOW. Windows does not,
# so there the link is followed, and a last check keeps the app from writing.
@pytest.mark.parametrize("o_nofollow", [True, False])
@pytest.mark.parametrize("already_have", [b"", b"da"])  # a fresh .part file is truncated, a resumed one appended to
def test_a_link_that_appears_during_the_request_is_skipped_at_once(dirs, fake_nas, connect, monkeypatch,
                                                                   o_nofollow, already_have):
    dest, outside = dirs
    target = _outside_file(outside)
    part = dest / "a.txt.part"
    if already_have:
        part.write_bytes(already_have)
    if not o_nofollow:
        monkeypatch.setattr(client_module, "_PART_FLAGS",
                            client_module._PART_FLAGS & ~getattr(os, "O_NOFOLLOW", 0))
    nas = _nas(fake_nas)

    def swap_in_a_link():
        if already_have:
            os.remove(str(part))
        _link(target, part)

    nas.on_download = swap_in_a_link
    logs = []
    _no_sleep(monkeypatch)

    ok = connect(nas, log=logs.append).download_file("/share/a.txt", str(dest / "a.txt"), 4)

    assert ok is SKIPPED
    assert _untouched(target)
    assert len(_downloads(nas)) == 1
    assert any(m.startswith("Skipped (symbolic link) ") for m in logs)
    assert not any("retry" in m for m in logs)


def test_a_link_that_appears_before_a_retry_is_skipped(dirs, fake_nas, connect, monkeypatch):
    dest, outside = dirs
    target = _outside_file(outside)
    nas = _nas(fake_nas)

    def drop_the_connection():
        if not os.path.lexists(str(dest / "a.txt.part")):
            _link(target, dest / "a.txt.part")
        raise requests.ConnectionError("connection dropped")

    nas.on_download = drop_the_connection
    logs = []
    monkeypatch.setattr(client_module.time, "sleep", lambda _s: None)

    ok = connect(nas, log=logs.append).download_file("/share/a.txt", str(dest / "a.txt"), 4)

    assert ok is SKIPPED
    assert _untouched(target)
    assert len(_downloads(nas)) == 1
    assert any(m.startswith("Skipped (symbolic link) ") for m in logs)


# ---- hard links -------------------------------------------------------------

def test_a_part_file_with_another_hard_link_is_skipped(dirs, fake_nas, connect):
    dest, outside = dirs
    target = _outside_file(outside)
    _hard_link(target, dest / "a.txt.part")
    logs = []
    nas = _nas(fake_nas)

    ok = connect(nas, log=logs.append).download_file("/share/a.txt", str(dest / "a.txt"), 4)

    assert ok is SKIPPED
    assert _untouched(target)
    assert _downloads(nas) == []
    assert not (dest / "a.txt").exists()
    assert (dest / "a.txt.part").exists()  # nothing is removed either
    assert _says_how_to_recover(logs)


def test_deleting_the_part_file_lets_the_download_run_again(dirs, fake_nas, connect):
    dest, outside = dirs
    target = _outside_file(outside)
    _hard_link(target, dest / "a.txt.part")
    client = connect(_nas(fake_nas))
    assert client.download_file("/share/a.txt", str(dest / "a.txt"), 4) is SKIPPED

    os.remove(str(dest / "a.txt.part"))  # what the skip line says to do

    assert client.download_file("/share/a.txt", str(dest / "a.txt"), 4) is True
    assert (dest / "a.txt").read_bytes() == b"data"
    assert _untouched(target)


def test_a_hard_link_that_appears_during_the_request_is_skipped(dirs, fake_nas, connect, monkeypatch):
    dest, outside = dirs
    target = _outside_file(outside)
    nas = _nas(fake_nas)
    nas.on_download = lambda: _hard_link(target, dest / "a.txt.part")
    logs = []
    _no_sleep(monkeypatch)

    ok = connect(nas, log=logs.append).download_file("/share/a.txt", str(dest / "a.txt"), 4)

    assert ok is SKIPPED
    assert _untouched(target)  # opened, but not truncated or written
    assert _says_how_to_recover(logs)


def test_a_complete_file_with_another_hard_link_is_not_restamped(dirs, fake_nas, connect):
    dest, outside = dirs
    target = _outside_file(outside, b"data")
    _hard_link(target, dest / "a.txt")

    ok = connect(_nas(fake_nas)).download_file("/share/a.txt", str(dest / "a.txt"), 4, mtime=2_000_000_000)

    assert ok is True
    assert _untouched(target, b"data")


def test_replacing_a_hard_linked_file_leaves_its_other_name_alone(dirs, fake_nas, connect):
    dest, outside = dirs
    target = _outside_file(outside)
    _hard_link(target, dest / "a.txt")

    ok = connect(_nas(fake_nas, b"newer")).download_file("/share/a.txt", str(dest / "a.txt"), 5,
                                                         mtime=2_000_000_000)

    assert ok is True
    assert (dest / "a.txt").read_bytes() == b"newer"
    assert _untouched(target)


def test_apply_file_times_does_not_follow_a_symbolic_link(dirs):
    dest, outside = dirs
    target = _outside_file(outside)
    _link(target, dest / "a.txt")
    apply_file_times(str(dest / "a.txt"), mtime=2_000_000_000)
    assert _untouched(target)


# ---- bytes arrive unchanged -------------------------------------------------

PAYLOAD = b"line one\nline two\r\nline three\r\x1a\x00\n" * 500


@pytest.mark.parametrize("already_have", [0, 7])
def test_a_payload_with_newline_bytes_is_byte_identical(dirs, fake_nas, connect, already_have):
    dest, _ = dirs
    if already_have:
        (dest / "a.txt.part").write_bytes(PAYLOAD[:already_have])
    client = connect(_nas(fake_nas, PAYLOAD))

    assert client.download_file("/share/a.txt", str(dest / "a.txt"), len(PAYLOAD)) is True

    assert (dest / "a.txt").read_bytes() == PAYLOAD
