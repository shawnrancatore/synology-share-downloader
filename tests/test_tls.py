# Copyright 2026 Dynamo Foundry LLC
# Licensed under the Apache License, Version 2.0.
"""Which addresses get a verified TLS connection, and what happens when one doesn't."""
import os
import subprocess
import sys
import warnings

import pytest
import requests
from urllib3.exceptions import InsecureRequestWarning

from synology_share_downloader.client import ShareError, SynoShareClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARE_URL = "http://gofile.me/AbCdE/ExAmPlE123"

# What the QuickConnect coordinator says about a NAS (synthetic values).
SERVER_INFO = {
    "errno": 0,
    "server": {
        "external": {"ip": "203.0.113.7"},
        "ddns": "nas.example.com",
        "interface": [{"ip": "192.0.2.10"}, {"ip": ""}],
    },
    "service": {"port": 5001, "ext_port": 5443},
    "smartdns": {"external": "smartdns.example.com", "lan": ["lan.example.com"]},
}

EXPECTED_CANDIDATES = [
    ("smartdns.example.com", 5443, True, "direct (secure name)"),
    ("203.0.113.7", 5443, False, "direct IP"),
    ("nas.example.com", 5001, False, "DDNS"),
    ("nas.example.com", 5443, False, "DDNS"),
    ("lan.example.com", 5001, True, "LAN"),
    ("192.0.2.10", 5001, False, "LAN IP"),
]


class _Probe:
    def __init__(self, body):
        self.ok = True
        self._body = body

    def json(self):
        return self._body


@pytest.fixture
def network(monkeypatch):
    """Fake the coordinator and the probes. Set .reachable to the bases that answer."""
    class Net:
        reachable = set()
        coordinator_calls = []
        probes = []

    net = Net()

    def fake_post(url, data=None, timeout=None, **kwargs):
        net.coordinator_calls.append((url, kwargs.get("verify", True)))
        return _Probe([SERVER_INFO])

    def fake_get(url, params=None, verify=True, timeout=None, **kwargs):
        base = url.rsplit("/webapi/", 1)[0]
        net.probes.append((base, verify))
        if base in net.reachable:
            return _Probe({"success": True})
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)
    return net


def test_candidate_order_and_verify_flags():
    client = SynoShareClient(SHARE_URL, "pw")
    assert client._candidates(SERVER_INFO) == EXPECTED_CANDIDATES


def test_resolve_probes_each_address_in_order_with_its_verify_flag(network):
    client = SynoShareClient(SHARE_URL, "pw")
    with pytest.raises(ShareError):
        client.resolve()
    assert network.probes == [("https://%s:%s" % (h, p), v) for h, p, v, _ in EXPECTED_CANDIDATES]


def test_the_coordinator_is_always_verified(network):
    client = SynoShareClient(SHARE_URL, "pw")
    with pytest.raises(ShareError):
        client.resolve()
    assert network.coordinator_calls and all(v is True for _, v in network.coordinator_calls)


def test_resolve_prefers_the_verified_smartdns_name(network):
    logs = []
    network.reachable = {"https://smartdns.example.com:5443", "https://203.0.113.7:5443"}
    client = SynoShareClient(SHARE_URL, "pw", log=logs.append)
    client.resolve()
    assert (client.base, client.verify, client.host) == (
        "https://smartdns.example.com:5443", True, "smartdns.example.com")
    assert not any("certificate not verified" in m for m in logs)


def test_fallback_to_an_unverified_address_is_logged(network):
    logs = []
    network.reachable = {"https://203.0.113.7:5443"}
    client = SynoShareClient(SHARE_URL, "pw", log=logs.append)
    client.resolve()
    assert (client.base, client.verify, client.host) == ("https://203.0.113.7:5443", False, "203.0.113.7")
    assert any("certificate not verified for 203.0.113.7" in m for m in logs)


def test_lan_ip_fallback_is_logged(network):
    logs = []
    network.reachable = {"https://192.0.2.10:5001"}
    client = SynoShareClient(SHARE_URL, "pw", log=logs.append)
    client.resolve()
    assert client.verify is False
    assert any("certificate not verified for 192.0.2.10" in m for m in logs)


def _login_calls(nas):
    return [c for c in nas.calls if c[2] == "SYNO.Core.Sharing.Login"]


def test_unverified_login_asks_first_and_stops_on_no(fake_nas, connect):
    nas = fake_nas({"/share": []}, {})
    asked = []
    client = connect(nas, verify=False,
                     confirm_unverified=lambda host: asked.append(host) or False)
    with pytest.raises(ShareError):
        client.login()
    assert asked == ["nas.example.com"]
    assert _login_calls(nas) == []  # the password never left


def test_unverified_login_goes_ahead_on_yes(fake_nas, connect):
    nas = fake_nas({"/share": []}, {})
    client = connect(nas, verify=False, confirm_unverified=lambda host: True)
    client.login()
    assert [c[3] for c in _login_calls(nas)] == [False]
    client.list_folder("/share")
    assert all(c[3] is False for c in nas.calls)


def test_verified_login_does_not_ask(fake_nas, connect):
    nas = fake_nas({"/share": []}, {})
    asked = []
    client = connect(nas, verify=True, confirm_unverified=lambda host: asked.append(host) or False)
    client.login()
    assert asked == []
    assert all(c[3] is True for c in nas.calls)


def test_importing_the_client_does_not_silence_insecure_warnings():
    # Run in a fresh interpreter: pytest resets warning filters between
    # collection and the tests, which would hide an import-time change.
    code = (
        "import warnings, urllib3\n"
        "import synology_share_downloader.client\n"
        "with warnings.catch_warnings(record=True) as caught:\n"
        "    warnings.warn(\"Unverified HTTPS request is being made to host 'other.example.com'.\",\n"
        "                  urllib3.exceptions.InsecureRequestWarning)\n"
        "print(len(caught))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONWARNINGS"}
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "1"


def test_the_warning_is_quieted_only_for_the_unverified_host(network):
    network.reachable = {"https://203.0.113.7:5443"}
    SynoShareClient(SHARE_URL, "pw").resolve()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", append=True)
        for host in ("203.0.113.7", "other.example.com"):
            warnings.warn("Unverified HTTPS request is being made to host '%s'. "
                          "Adding certificate verification is strongly advised." % host,
                          InsecureRequestWarning)
    assert [str(w.message).split("'")[1] for w in caught] == ["other.example.com"]
