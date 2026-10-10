# Copyright 2026 Dynamo Foundry LLC
# Licensed under the Apache License, Version 2.0.
"""GUI logic that runs without a display, on a bare App (no Tk window)."""
import os
import queue
import threading

import pytest

gui = pytest.importorskip("synology_share_downloader.gui")  # needs tkinter

OLD = 1_000_000_000


def _bare_app(client=None):
    app = gui.App.__new__(gui.App)
    app.q = queue.Queue()
    app.stop_flag = threading.Event()
    app.unverified_ok = set()
    app.client = client
    return app


def _logged(app):
    out = []
    while not app.q.empty():
        kind, payload = app.q.get_nowait()
        if kind in ("log", "dl_done"):
            out.append(payload)
    return out


def test_download_worker_does_not_restamp_through_a_link(tmp_path, fake_nas, connect):
    dest = tmp_path / "dest"
    (dest / "share").mkdir(parents=True)
    other = dest / "share" / "other.txt"
    other.write_bytes(b"keep")
    os.utime(str(other), (OLD, OLD))
    try:
        os.symlink(str(other), str(dest / "share" / "a.txt"))
    except (OSError, NotImplementedError):
        pytest.skip("this system does not let us create a symlink")
    nas = fake_nas({"/share": [("a.txt", "/share/a.txt", False)]}, {"/share/a.txt": b"data"})
    app = _bare_app(connect(nas))
    app.client._log = app.log_msg

    root = {"path": "/share", "isdir": True, "size": 0, "mtime": None, "crtime": None}
    app._download_worker([root], str(dest), False, 1)

    assert other.read_bytes() == b"keep"
    assert os.stat(str(other)).st_mtime == OLD
    assert os.path.islink(str(dest / "share" / "a.txt"))
    assert any(m.startswith("Skipped ") and "link" in m for m in _logged(app))


def _asking(app, answers):
    """Stub App._ask: record each question, answer from the list."""
    asked = []
    replies = iter(answers)

    def ask(kind, payload):
        asked.append((kind, payload))
        return next(replies)

    app._ask = ask
    return asked


def test_confirm_unverified_asks_once_per_host():
    app = _bare_app()
    asked = _asking(app, [True, True])
    assert app._confirm_unverified("203.0.113.7")
    assert app._confirm_unverified("203.0.113.7")
    assert app._confirm_unverified("192.0.2.10")
    assert app._confirm_unverified("192.0.2.10")
    assert asked == [("ask_unverified", "203.0.113.7"), ("ask_unverified", "192.0.2.10")]


def test_no_stops_the_login_and_the_next_connect_asks_again(fake_nas, connect):
    from synology_share_downloader.client import ShareError

    app = _bare_app()
    asked = _asking(app, [False, True])
    nas = fake_nas({"/share": []}, {})
    client = connect(nas, verify=False, confirm_unverified=app._confirm_unverified)

    with pytest.raises(ShareError, match="password was not sent"):
        client.login()
    assert [c for c in nas.calls if c[2] == "SYNO.Core.Sharing.Login"] == []

    client.login()
    assert asked == [("ask_unverified", "nas.example.com")] * 2
    assert len([c for c in nas.calls if c[2] == "SYNO.Core.Sharing.Login"]) == 1
