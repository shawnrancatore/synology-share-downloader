# Copyright 2026 Dynamo Foundry LLC
# Licensed under the Apache License, Version 2.0.
"""The app never writes through a link: not the file, not its .part file."""
import os

import pytest

from synology_share_downloader.plan import UnsafePathError, safe_local_path

OLD = 1_000_000_000  # an mtime far in the past


def _link(target, link):
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError):
        pytest.skip("this system does not let us create a symlink")


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

    assert ok is False
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

    assert ok is False
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
