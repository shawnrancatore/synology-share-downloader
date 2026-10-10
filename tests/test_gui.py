# Copyright 2026 Dynamo Foundry LLC
# Licensed under the Apache License, Version 2.0.
"""GUI logic that runs without a display, on a bare App (no Tk window)."""
import os
import queue
import threading
import types

import pytest

pytest.importorskip("tkinter")  # no Tk on this Python: skip. Any other import error fails.

from synology_share_downloader import gui  # noqa: E402

OLD = 1_000_000_000

# Ways a user might paste a link; none may reach the log with the share's id.
PASTED_LINKS = [
    "http://gofile.me/AbCdE/ExAmPlE123",
    "gofile.me/AbCdE/ExAmPlE123",
    "https://acme.quickconnect.to/sharing/ExAmPlE123",
    "http://gofile.me/AbCdE/ExAmPlE123/;x",
    "http://gofile.me/AbCdE/ExAmPlE123/x",
    "gofile.me\\AbCdE\\ExAmPlE123",
    "http%3A%2F%2Fgofile.me%2FAbCdE%2FExAmPlE123",
    "gofile.me%2FAbCdE%2FExAmPlE123",
    "gofile.me%5CAbCdE%5CExAmPlE123",
    "https://192.0.2.10:5001/sharing/ExAmPlE123/index.html",
    "gofile.me/ExAmPlE123",
    "http://[ExAmPlE123]/AbCdE/x",
    "ExAmPlE123",
    # A tab or a line break, pasted or percent-encoded.
    "gofile.me\nExAmPlE123",
    "gofile.me\tExAmPlE123",
    "gofile.me\r\nExAmPlE123",
    "gofile.me%0AExAmPlE123",
    "gofile.me%09ExAmPlE123",
    "gofile.me%250AExAmPlE123",
    "gofile.me\nAbCdE\nExAmPlE123",
    "http://gofile.me\nAbCdE\nExAmPlE123",
    "gofile.me/AbCdE\tExAmPlE123/x",
]


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
    logged = _logged(app)
    assert any(m.startswith("Skipped (symbolic link) ") for m in logged)
    assert logged[-1].startswith("Done. 0 file(s) downloaded; 1 link(s) skipped")


def test_download_worker_counts_a_hard_linked_part_file_as_skipped(tmp_path, fake_nas, connect):
    dest, outside = tmp_path / "dest", tmp_path / "outside"
    (dest / "share").mkdir(parents=True)
    outside.mkdir()
    target = outside / "target.txt"
    target.write_bytes(b"keep")
    os.utime(str(target), (OLD, OLD))
    try:
        os.link(str(target), str(dest / "share" / "a.txt.part"))
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("this system does not let us create a hard link")
    nas = fake_nas({"/share": [("a.txt", "/share/a.txt", False), ("b.txt", "/share/b.txt", False)]},
                   {"/share/a.txt": b"data", "/share/b.txt": b"more"})
    app = _bare_app(connect(nas))
    app.client._log = app.log_msg

    root = {"path": "/share", "isdir": True, "size": 0, "mtime": None, "crtime": None}
    app._download_worker([root], str(dest), False, 2)

    assert target.read_bytes() == b"keep" and os.stat(str(target)).st_mtime == OLD
    assert (dest / "share" / "b.txt").read_bytes() == b"more"
    logged = _logged(app)
    assert any(m.startswith("Skipped (hard link) ") for m in logged)
    assert logged[-1].startswith("Done. 1 file(s) downloaded; 1 link(s) skipped")


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


# ---- connect: the log never shows the share's id ---------------------------

class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Widget:
    def configure(self, **_kw):
        pass

    def get_children(self):
        return []


class _InlineThread:
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


def _connect(monkeypatch, url, client_class):
    """Run App.on_connect() for url with client_class; return everything it logged."""
    monkeypatch.setattr(gui, "SynoShareClient", client_class)
    monkeypatch.setattr(gui, "threading", types.SimpleNamespace(Thread=_InlineThread))
    app = _bare_app()
    app.downloading = False
    app.nodes = {}
    app.url_var, app.pw_var = _Var(url), _Var("pw")
    app.connect_btn = app.download_btn = app.tree = _Widget()
    shown = []
    app._append_log = shown.append
    app.on_connect()
    while not app.q.empty():
        shown.append(str(app.q.get_nowait()[1]))
    return shown


class _Unreachable(gui.SynoShareClient):
    """A real client whose resolve() fails with an error that quotes the link."""

    def resolve(self):
        raise RuntimeError("no route to %s (_sharing_id=%%22%s%%22)" % (self.share_url, self.link_id))


def _broken_client(url, *args, **kwargs):
    raise ValueError("cannot read %r" % url)


@pytest.mark.parametrize("url", PASTED_LINKS)
@pytest.mark.parametrize("client_class", [_Unreachable, _broken_client])
def test_connecting_never_logs_the_share_id(monkeypatch, url, client_class):
    shown = _connect(monkeypatch, url, client_class)
    assert any(line.startswith("Connecting to ") for line in shown)
    assert not any("ExAmPlE123" in line for line in shown), shown


def test_an_unexpected_error_still_says_what_went_wrong(monkeypatch):
    shown = _connect(monkeypatch, "http://gofile.me/AbCdE/ExAmPlE123", _Unreachable)
    assert any(line.startswith("Unexpected error: no route to ") for line in shown)


NOT_A_LINK = ("That doesn't look like a Synology share link.\n"
              "Expected something like: http://gofile.me/XXXXX/YYYYYYYYY")


@pytest.mark.parametrize("paste", [
    "<http://gofile.me/AbCdE/ExAmPlE123>",
    "Link: http://gofile.me/AbCdE/ExAmPlE123",
    '"http://gofile.me/AbCdE/ExAmPlE123"',
    "http:/gofile.me/AbCdE/ExAmPlE123",
    "not a link",
    # A piece of the message itself.
    "http://gofile.me/",
    "http://",
    "link",
    ".",
])
def test_a_paste_that_is_not_a_link_gets_the_apps_message_as_written(monkeypatch, paste):
    shown = _connect(monkeypatch, paste, _Unreachable)
    assert NOT_A_LINK in shown
    assert not any("ExAmPlE123" in line for line in shown), shown
