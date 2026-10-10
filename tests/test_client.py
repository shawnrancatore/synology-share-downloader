# Copyright 2026 Dynamo Foundry LLC
# Licensed under the Apache License, Version 2.0.
import os
import time

import pytest
import requests

from synology_share_downloader import __version__
from synology_share_downloader import client as client_module
from synology_share_downloader.client import (
    ShareError,
    SynoShareClient,
    apply_file_times,
    hide_share_link,
    parse_share_url,
    redact_share_url,
)

# Obviously fake share links: never a real share.


def test_parse_gofile():
    assert parse_share_url("http://gofile.me/AbCdE/ExAmPlE123") == ("AbCdE", "ExAmPlE123", True)


def test_parse_gofile_no_scheme():
    assert parse_share_url("gofile.me/AbCdE/ExAmPlE123") == ("AbCdE", "ExAmPlE123", True)


def test_parse_quickconnect_path():
    assert parse_share_url("https://quickconnect.to/AbCdE/ExAmPlE123") == ("AbCdE", "ExAmPlE123", False)


def test_parse_quickconnect_subdomain():
    qc, link, gofile = parse_share_url("https://acme.quickconnect.to/sharing/ExAmPlE123")
    assert qc == "acme"
    assert link == "ExAmPlE123"
    assert gofile is False


def test_parse_bad_url():
    with pytest.raises(ShareError):
        parse_share_url("https://example.com/whatever")


def test_apply_file_times(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("hello")
    when = time.time() - 86400 * 365  # one year ago
    apply_file_times(str(p), mtime=when)
    assert abs(os.path.getmtime(str(p)) - when) < 2


# (what the user pasted, what the log may show). The id never appears.
REDACTIONS = [
    ("http://gofile.me/AbCdE/ExAmPlE123", "http://gofile.me/AbCdE/\u2026"),
    ("gofile.me/AbCdE/ExAmPlE123", "gofile.me/AbCdE/\u2026"),
    ("  https://gofile.me/AbCdE/ExAmPlE123/  ", "https://gofile.me/AbCdE/\u2026"),
    ("https://quickconnect.to/AbCdE/ExAmPlE123", "https://quickconnect.to/AbCdE/\u2026"),
    ("https://acme.quickconnect.to/sharing/ExAmPlE123", "https://acme.quickconnect.to/sharing/\u2026"),
    ("http://gofile.me/AbCdE/ExAmPlE123?x=ExAmPlE123#ExAmPlE123", "http://gofile.me/AbCdE/\u2026"),
    ("http://you@example.com/AbCdE/ExAmPlE123", "http://example.com/AbCdE/\u2026"),
    # Path parameters and backslashes.
    ("http://gofile.me/AbCdE/ExAmPlE123/;x", "http://gofile.me/AbCdE/\u2026"),
    ("http://gofile.me/AbCdE/ExAmPlE123;x", "http://gofile.me/AbCdE/\u2026"),
    ("gofile.me\\AbCdE\\ExAmPlE123", "gofile.me/AbCdE/\u2026"),
    ("http://gofile.me\\AbCdE\\ExAmPlE123", "http://gofile.me/AbCdE/\u2026"),
    ("http://gofile.me/AbCdE\\ExAmPlE123", "http://gofile.me/AbCdE/\u2026"),
    ("http://gofile.me/AbCdE/ExAmPlE123\\", "http://gofile.me/AbCdE/\u2026"),
    # Percent-encoded, once or more.
    ("http%3A%2F%2Fgofile.me%2FAbCdE%2FExAmPlE123", "http://gofile.me/AbCdE/\u2026"),
    ("gofile.me%2FAbCdE%2FExAmPlE123", "gofile.me/AbCdE/\u2026"),
    ("gofile.me%5CAbCdE%5CExAmPlE123", "gofile.me/AbCdE/\u2026"),
    ("http://gofile.me/AbCdE%5CExAmPlE123", "http://gofile.me/AbCdE/\u2026"),
    ("gofile.me%255CAbCdE%255CExAmPlE123", "gofile.me/AbCdE/\u2026"),
    ("gofile.me/AbCdE/%45xAmPlE123", "gofile.me/AbCdE/\u2026"),
    ("gofile.me%2525252FAbCdE%2525252FExAmPlE123", "\u2026"),
    # The id is not the last segment, or is the only one.
    ("http://gofile.me/AbCdE/ExAmPlE123/x", "http://gofile.me/AbCdE/\u2026"),
    ("https://192.0.2.10:5001/sharing/ExAmPlE123/index.html", "https://192.0.2.10:5001/sharing/\u2026"),
    ("gofile.me/ExAmPlE123", "gofile.me/\u2026"),
    ("gofile.me/ExAmPlE123/ExAmPlE123", "gofile.me/\u2026/\u2026"),
    ("http://gofile.me/AbCdE;ExAmPlE123/x", "http://gofile.me/\u2026"),
    ("http://gofile.me/AbCdE ExAmPlE123/x", "http://gofile.me/\u2026"),
    # Not a plain host and path: nothing of it is shown.
    ("ExAmPlE123", "\u2026"),
    ("", "\u2026"),
    ("http://[bad/ExAmPlE123", "\u2026"),
    ("http://[ExAmPlE123]/AbCdE/x", "\u2026"),
    ("http://gofile.me:ExAmPlE123/AbCdE/x", "\u2026"),
    ("ftp://gofile.me/AbCdE/ExAmPlE123", "\u2026"),
    ("Link: http://gofile.me/AbCdE/ExAmPlE123", "\u2026"),
    # Nothing secret to hide.
    ("http://gofile.me", "http://gofile.me"),
]


@pytest.mark.parametrize("url, logged", REDACTIONS)
def test_redact_share_url_never_shows_the_share_id(url, logged):
    assert redact_share_url(url) == logged
    assert "ExAmPlE123" not in redact_share_url(url)


@pytest.mark.parametrize("url", [u for u, _ in REDACTIONS])
def test_a_link_that_does_not_parse_is_refused_without_quoting_it(url):
    try:
        parse_share_url(url)
    except ShareError as e:
        assert "ExAmPlE123" not in str(e)


@pytest.mark.parametrize("url", [u for u, _ in REDACTIONS if "xAmPlE123" in u])
def test_hide_share_link_cleans_text_that_quotes_the_link(url):
    for text in ("cannot open %s" % url, "cannot open %r" % url,
                 "bad id ExAmPlE123", "_sharing_id=%22ExAmPlE123%22"):
        assert "ExAmPlE123" not in hide_share_link(text, url)


def test_hide_share_link_keeps_the_rest_of_the_message():
    url = "http://gofile.me/AbCdE/ExAmPlE123"
    assert hide_share_link("Max retries exceeded for %s (host gofile.me)" % url, url) == (
        "Max retries exceeded for http://gofile.me/AbCdE/\u2026 (host gofile.me)")


def test_download_errors_do_not_log_the_link_id(tmp_path, monkeypatch, fake_nas, connect):
    logs = []
    client = connect(fake_nas({}, {}), log=logs.append)

    def unreachable(*args, **kwargs):
        raise requests.ConnectionError(
            "HTTPSConnectionPool(host='nas.example.com', port=5001): Max retries exceeded with url: "
            "/sharing/webapi/entry.cgi?api=SYNO.FolderSharing.Download&_sharing_id=%22ExAmPlE123%22")

    client.session.get = unreachable
    monkeypatch.setattr(client_module.time, "sleep", lambda _s: None)
    with pytest.raises(ShareError) as err:
        client.download_file("/share/a.txt", str(tmp_path / "a.txt"), retries=2)
    assert "ExAmPlE123" not in str(err.value)
    assert logs and not any("ExAmPlE123" in m for m in logs)


def test_user_agent_carries_the_version():
    client = SynoShareClient("http://gofile.me/AbCdE/ExAmPlE123", "pw")
    assert client.session.headers["User-Agent"] == "SynologyShareDownloader/" + __version__


def test_scrubbing_a_short_link_id_leaves_other_words_alone():
    client = SynoShareClient("http://gofile.me/AbCdE/x", "pw")
    text = ("HTTPSConnectionPool(host='nas.example.com', port=5001): Max retries exceeded with url: "
            "/sharing/webapi/entry.cgi?api=SYNO.FolderSharing.Download&_sharing_id=%22x%22&path=x")
    assert client.scrub(text) == (
        "HTTPSConnectionPool(host='nas.example.com', port=5001): Max retries exceeded with url: "
        "/sharing/webapi/entry.cgi?api=SYNO.FolderSharing.Download&_sharing_id=…&path=…")
