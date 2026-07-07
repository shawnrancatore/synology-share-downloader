# Copyright 2026 Dynamo Foundry LLC
# Licensed under the Apache License, Version 2.0.
from synology_share_downloader.util import format_eta, human_size


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(512) == "512 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(1024 * 1024) == "1.0 MB"
    assert human_size(5 * 1024 ** 3) == "5.0 GB"


def test_format_eta():
    assert format_eta(0) == "0s"
    assert format_eta(45) == "45s"
    assert format_eta(90) == "1m 30s"
    assert format_eta(3725) == "1h 02m"
    assert format_eta(-5) == "0s"
