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


@pytest.mark.parametrize("url, logged", [
    ("http://gofile.me/AbCdE/ExAmPlE123", "http://gofile.me/AbCdE/\u2026"),
    ("gofile.me/AbCdE/ExAmPlE123", "gofile.me/AbCdE/\u2026"),
    ("  https://gofile.me/AbCdE/ExAmPlE123/  ", "https://gofile.me/AbCdE/\u2026"),
    ("https://quickconnect.to/AbCdE/ExAmPlE123", "https://quickconnect.to/AbCdE/\u2026"),
    ("https://acme.quickconnect.to/sharing/ExAmPlE123", "https://acme.quickconnect.to/sharing/\u2026"),
    ("http://gofile.me/AbCdE/ExAmPlE123?x=ExAmPlE123#ExAmPlE123", "http://gofile.me/AbCdE/\u2026"),
    ("http://you@example.com/AbCdE/ExAmPlE123", "http://example.com/AbCdE/\u2026"),
    ("http://[bad/ExAmPlE123", "\u2026"),
    ("", ""),
])
def test_redact_share_url_hides_the_last_segment(url, logged):
    assert redact_share_url(url) == logged
    assert "ExAmPlE123" not in redact_share_url(url)


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
    assert client._scrub(text) == (
        "HTTPSConnectionPool(host='nas.example.com', port=5001): Max retries exceeded with url: "
        "/sharing/webapi/entry.cgi?api=SYNO.FolderSharing.Download&_sharing_id=…&path=…")
