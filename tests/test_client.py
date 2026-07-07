# Copyright 2026 Dynamo Foundry LLC
# Licensed under the Apache License, Version 2.0.
import os
import time

import pytest

from synology_share_downloader.client import ShareError, apply_file_times, parse_share_url


def test_parse_gofile():
    assert parse_share_url("http://gofile.me/75lxK/7vqFT49uA") == ("75lxK", "7vqFT49uA", True)


def test_parse_gofile_no_scheme():
    assert parse_share_url("gofile.me/75lxK/7vqFT49uA") == ("75lxK", "7vqFT49uA", True)


def test_parse_quickconnect_path():
    assert parse_share_url("https://quickconnect.to/ABCDE/linkid123") == ("ABCDE", "linkid123", False)


def test_parse_quickconnect_subdomain():
    qc, link, gofile = parse_share_url("https://myserver.quickconnect.to/sharing/abc123")
    assert qc == "myserver"
    assert link == "abc123"
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
