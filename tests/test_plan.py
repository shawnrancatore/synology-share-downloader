# Copyright 2026 Dynamo Foundry LLC
# Licensed under the Apache License, Version 2.0.
"""A share's listing comes from the server, so its names are untrusted.

These tests feed hostile listings to the download planner and check that
nothing it plans to write lands outside the chosen destination.
"""
import ntpath
import os
import types

import pytest

from synology_share_downloader import plan as plan_module
from synology_share_downloader.plan import UnsafePathError, plan_downloads, safe_local_path

# Names a hostile share might list, in POSIX and Windows spellings. Each one
# is unsafe as a file name on at least one OS: it could step outside the
# destination folder, open a device, or write to a hidden file stream.
HOSTILE_NAMES = [
    "../x",
    "a/../../x",
    "/etc/x",
    "..",
    ".",
    "x\x00.txt",
    "..\\x",
    "a\\..\\..\\x",
    "C:\\x",
    "C:x",
    "c:/x",
    "\\x",
    "\\\\server\\share\\x",
    ".. ",
    # A colon: a drive to ntpath ("1:x" too), or an NTFS file stream.
    "1:x",
    "a:b",
    "foo::$DATA",
    "..::$INDEX_ALLOCATION",
    # Characters Windows does not allow, and control characters.
    "a<b",
    "a>b",
    'a"b',
    "a|b",
    "a?b",
    "a*b",
    "x -> y",
    "a\x01b",
    "a\x1fb",
    "a\tb",
    "a\nb",
    # A trailing dot or space: Windows drops it, so "a." would land on "a".
    "a.",
    "a ",
    "a.txt.",
    "a.txt ",
    "a. .",
    "dir./x",
    "dir /x",
]

# DOS device names: on Windows, opening one opens the device, with any
# extension, in any case, and with trailing dots or spaces.
DEVICE_NAMES = (["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"]
                + [p + d for p in ("COM", "LPT") for d in "0123456789\u00b9\u00b2\u00b3"])
HOSTILE_NAMES += DEVICE_NAMES + [
    "COM1.part",
    "LPT1.txt",
    "con",
    "Nul.txt",
    "AUX .txt",
    "CON.",
    "prn  ",
    "CONIN$.log",
    "com\u00b2.x",
]

# Odd but harmless names: they stay inside the destination.
BENIGN_NAMES = [
    "a.txt",
    "naïve résumé.pdf",
    "a..b",
    ".hidden",
    "...x",
    "CONSOLE.txt",
    "COM10",
    "LPT",
    "a.con",
    "nul-x.txt",
    "auxiliary",
    " leading space",
    "a .txt",
]


def _inside(path, root):
    root = os.path.realpath(root)
    real = os.path.realpath(path)
    return os.path.commonpath([root, real]) == root


def _entry(path, isdir=False, size=0, mtime=None):
    return {"name": path.rsplit("/", 1)[-1], "path": path, "isdir": isdir,
            "size": size, "mtime": mtime, "crtime": None}


class FakeShare:
    """Stands in for SynoShareClient: list_folder() answers from a dict."""

    def __init__(self, tree):
        self.tree = tree
        self.listed = []

    def list_folder(self, folder_path):
        self.listed.append(folder_path)
        return list(self.tree.get(folder_path, []))


def _pick_root(path="/share"):
    return [{"path": path, "isdir": True, "size": 0, "mtime": None, "crtime": None}]


# ---- safe_local_path ------------------------------------------------------

@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_safe_local_path_rejects_hostile_names(tmp_path, name):
    with pytest.raises(UnsafePathError):
        safe_local_path(str(tmp_path), "/share/" + name, "")


@pytest.mark.parametrize("name", BENIGN_NAMES)
def test_safe_local_path_keeps_benign_names_inside(tmp_path, name):
    local = safe_local_path(str(tmp_path), "/share/" + name, "")
    assert local == os.path.join(str(tmp_path), "share", name)
    assert _inside(local, tmp_path)


@pytest.fixture
def windows_paths(monkeypatch):
    """Use Windows path rules (ntpath) inside plan.py, whatever OS runs the test."""
    monkeypatch.setattr(plan_module, "os", types.SimpleNamespace(path=ntpath))


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_windows_rules_reject_hostile_names(windows_paths, name):
    with pytest.raises(UnsafePathError):
        safe_local_path("C:\\dest", "/share/" + name, "")


@pytest.mark.parametrize("name", BENIGN_NAMES)
def test_windows_rules_keep_benign_names_inside(windows_paths, name):
    local = safe_local_path("C:\\dest", "/share/" + name, "")
    assert local == "C:\\dest\\share\\" + name


@pytest.mark.parametrize("name, reason", [
    ("CON", "device"),
    ("COM1.part", "device"),
    ("LPT\u00b3.txt", "device"),
    ("foo::$DATA", "':'"),
    ("1:x", "':'"),
    ("a?b", "Windows does not allow"),
    ("a\x01b", "control character"),
    ("a.txt.", "ends with a dot or a space"),
    ("dir /x", "ends with a dot or a space"),
    ("..", "'.' or '..'"),
])
@pytest.mark.parametrize("rules", ["host", "windows"])
def test_the_logged_reason_is_the_real_one(request, name, reason, rules):
    if rules == "windows":
        request.getfixturevalue("windows_paths")
    dest = "C:\\dest" if rules == "windows" else str(request.getfixturevalue("tmp_path"))
    with pytest.raises(UnsafePathError) as err:
        safe_local_path(dest, "/share/" + name, "")
    assert reason in str(err.value)
    assert "link" not in str(err.value)


def test_safe_local_path_mirrors_folders(tmp_path):
    local = safe_local_path(str(tmp_path), "/share/photos/2024/a.jpg", "/share")
    assert local == os.path.join(str(tmp_path), "photos", "2024", "a.jpg")


def test_safe_local_path_rejects_paths_outside_the_remote_base(tmp_path):
    with pytest.raises(UnsafePathError):
        safe_local_path(str(tmp_path), "/etc/x", "/share")
    with pytest.raises(UnsafePathError):
        safe_local_path(str(tmp_path), "/shareevil/x", "/share")


def test_safe_local_path_rejects_a_link_out_of_the_destination(tmp_path):
    dest = tmp_path / "dest"
    outside = tmp_path / "outside"
    (dest / "share").mkdir(parents=True)
    outside.mkdir()
    try:
        os.symlink(str(outside), str(dest / "share" / "link"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this system does not let us create a symlink")
    with pytest.raises(UnsafePathError):
        safe_local_path(str(dest), "/share/link/x", "")


def test_safe_local_path_follows_a_linked_destination(tmp_path):
    real_dest = tmp_path / "real"
    real_dest.mkdir()
    try:
        os.symlink(str(real_dest), str(tmp_path / "dest"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this system does not let us create a symlink")
    local = safe_local_path(str(tmp_path / "dest"), "/share/a.txt", "")
    assert local == os.path.join(str(tmp_path / "dest"), "share", "a.txt")


# ---- plan_downloads -------------------------------------------------------

def test_plan_mirrors_a_normal_share(tmp_path):
    share = FakeShare({
        "/share": [_entry("/share/a.txt", size=5, mtime=100),
                   _entry("/share/sub", isdir=True),
                   _entry("/share/empty", isdir=True)],
        "/share/sub": [_entry("/share/sub/b.txt", size=7)],
    })
    plan = plan_downloads(share, _pick_root(), str(tmp_path))
    d = str(tmp_path)
    assert sorted(j[1] for j in plan.files) == sorted([
        os.path.join(d, "share", "a.txt"),
        os.path.join(d, "share", "sub", "b.txt"),
    ])
    assert sorted(f[0] for f in plan.folders) == sorted([
        os.path.join(d, "share"),
        os.path.join(d, "share", "sub"),
        os.path.join(d, "share", "empty"),
    ])
    assert plan.total_bytes == 12
    assert plan.skipped == []
    a_txt = [j for j in plan.files if j[0] == "/share/a.txt"][0]
    assert a_txt[2:4] == (5, 100)


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_plan_skips_hostile_file_names_and_logs_them(tmp_path, name):
    logs = []
    share = FakeShare({"/share": [_entry("/share/ok.txt", size=1),
                                  _entry("/share/" + name, size=1)]})
    plan = plan_downloads(share, _pick_root(), str(tmp_path), log=logs.append)
    assert [j[0] for j in plan.files] == ["/share/ok.txt"]
    assert [s[0] for s in plan.skipped] == ["/share/" + name]
    assert len(logs) == 1 and logs[0].startswith("Skipped ")
    assert repr("/share/" + name) in logs[0]
    for _, local, *_ in plan.files:
        assert _inside(local, tmp_path)


def test_plan_skips_entries_listed_outside_the_folder(tmp_path):
    logs = []
    share = FakeShare({"/share": [_entry("/etc/passwd", size=1)]})
    plan = plan_downloads(share, _pick_root(), str(tmp_path), log=logs.append)
    assert plan.files == []
    assert [s[0] for s in plan.skipped] == ["/etc/passwd"]


def test_plan_does_not_descend_into_a_hostile_folder(tmp_path):
    share = FakeShare({
        "/share": [_entry("/share/../evil", isdir=True)],
        "/share/../evil": [_entry("/share/../evil/x", size=1)],
    })
    plan = plan_downloads(share, _pick_root(), str(tmp_path), log=lambda _m: None)
    assert plan.files == []
    assert share.listed == ["/share"]
    assert [s[0] for s in plan.skipped] == ["/share/../evil"]


def test_plan_does_not_descend_through_a_link(tmp_path):
    dest = tmp_path / "dest"
    outside = tmp_path / "outside"
    (dest / "share").mkdir(parents=True)
    outside.mkdir()
    try:
        os.symlink(str(outside), str(dest / "share" / "link"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this system does not let us create a symlink")
    share = FakeShare({
        "/share": [_entry("/share/link", isdir=True)],
        "/share/link": [_entry("/share/link/x", size=1)],
    })
    plan = plan_downloads(share, _pick_root(), str(dest), log=lambda _m: None)
    assert plan.files == []
    assert share.listed == ["/share"]


@pytest.mark.parametrize("root", ["/..", "/a/..", "/C:"])
def test_plan_skips_a_hostile_pick(tmp_path, root):
    share = FakeShare({root: [_entry(root + "/x", size=1)]})
    plan = plan_downloads(share, _pick_root(root), str(tmp_path), log=lambda _m: None)
    assert plan.files == [] and plan.folders == []
    assert share.listed == []


def test_plan_picked_file_keeps_its_times(tmp_path):
    pick = {"path": "/share/sub/a.txt", "isdir": False, "size": 3,
            "mtime": 1000, "crtime": 900}
    plan = plan_downloads(FakeShare({}), [pick], str(tmp_path))
    assert plan.files == [("/share/sub/a.txt", os.path.join(str(tmp_path), "a.txt"),
                           3, 1000, 900)]


def test_plan_stops_when_asked(tmp_path):
    share = FakeShare({"/share": [_entry("/share/a.txt", size=1)]})
    plan = plan_downloads(share, _pick_root(), str(tmp_path), stop=lambda: True)
    assert plan.files == []


# ---- end to end: a hostile share, through the real client -----------------

def test_hostile_share_writes_nothing_outside_the_destination(tmp_path, fake_nas, connect):
    hostile = ["../../escape.txt", "..\\..\\win.txt", "C:\\x.txt", "C:x.txt"]
    folders = {
        "/share": [("ok.txt", "/share/ok.txt", False),
                   ("evil", "/share/../evil", True),
                   ("abs.txt", "/tmp/abs.txt", False)]
        + [(n, "/share/" + n, False) for n in hostile],
        "/share/../evil": [("x.txt", "/share/../evil/x.txt", False)],
    }
    files = {p: b"data" for p in ["/share/ok.txt", "/tmp/abs.txt", "/share/../evil/x.txt"]
             + ["/share/" + n for n in hostile]}
    nas = fake_nas(folders, files)
    logs = []
    client = connect(nas, log=logs.append)
    dest = tmp_path / "a" / "b" / "dest"
    dest.mkdir(parents=True)

    plan = plan_downloads(client, _pick_root(), str(dest), log=logs.append)
    for remote, local, size, mtime, crtime in plan.files:
        assert client.download_file(remote, local, size, mtime=mtime, crtime=crtime)

    written = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    assert written == [os.path.join("a", "b", "dest", "share", "ok.txt")]
    assert len(plan.skipped) == 6
    assert sum(m.startswith("Skipped ") for m in logs) == 6
