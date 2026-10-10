# Copyright 2026 Dynamo Foundry LLC
# Licensed under the Apache License, Version 2.0.
"""A fake NAS for tests: answers the Synology share API with no network."""
import json

import pytest

# Obviously fake: never a real share.
SHARE_URL = "http://gofile.me/AbCdE/ExAmPlE123"
LINK_ID = "ExAmPlE123"


class FakeResponse:
    def __init__(self, status=200, body=None, content=b"", headers=None):
        self.status_code = status
        self._body = body
        self._content = content
        self.headers = dict(headers or {})

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._body

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def close(self):
        pass


class FakeNAS:
    """Folders and files of a share, served the way SYNO.FolderSharing does.

    folders maps a folder path to its entries: (name, path, isdir).
    files maps a file path to its bytes.
    """

    def __init__(self, folders, files, password="pw"):
        self.folders = folders
        self.files = files
        self.password = password
        self.calls = []
        self.on_download = None  # called when a download request arrives; may raise

    def _entry(self, name, path, isdir):
        size = 0 if isdir else len(self.files.get(path, b""))
        return {"name": name, "path": path, "isdir": isdir,
                "additional": {"size": size, "time": {"mtime": 1000, "crtime": 900}}}

    def handle(self, method, url, args, verify, headers=None):
        self.calls.append((method, url, args.get("api"), verify))
        api = args.get("api")
        if api == "SYNO.Core.Sharing.Login":
            ok = args.get("password") == self.password
            return FakeResponse(body={"success": ok} if ok else
                                {"success": False, "error": {"code": 1001}})
        if api == "SYNO.Core.Sharing.Initdata":
            return FakeResponse(body={"success": True, "data": {
                "Private": {"filename": "share"}, "Sharing": {"app": {"is_folder": True}}}})
        if api == "SYNO.FolderSharing.List":
            folder = json.loads(args["folder_path"])
            entries = [self._entry(*e) for e in self.folders.get(folder, [])]
            return FakeResponse(body={"success": True,
                                      "data": {"files": entries, "total": len(entries)}})
        if api == "SYNO.FolderSharing.Download":
            if self.on_download:
                self.on_download()
            path = json.loads(args["path"])[0]
            content = self.files[path]
            status = 200
            rng = (headers or {}).get("Range", "")
            if rng.startswith("bytes=") and rng.endswith("-"):
                content, status = content[int(rng[6:-1]):], 206
            return FakeResponse(status=status, content=content, headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(content))})
        return FakeResponse(status=404, body={"success": False})


class FakeSession:
    def __init__(self, nas):
        self.nas = nas
        self.headers = {}

    def post(self, url, data=None, headers=None, verify=True, timeout=None, stream=False):
        return self.nas.handle("POST", url, data or {}, verify, headers)

    def get(self, url, params=None, headers=None, verify=True, timeout=None, stream=False):
        return self.nas.handle("GET", url, params or {}, verify, headers)


@pytest.fixture
def fake_nas():
    """Return a factory: fake_nas(folders, files) -> FakeNAS."""
    return FakeNAS


@pytest.fixture
def connect():
    """Return a SynoShareClient wired to a FakeNAS, as if resolve() had run."""
    from synology_share_downloader.client import SynoShareClient

    def make(nas, verify=True, log=None, **kwargs):
        client = SynoShareClient(SHARE_URL, nas.password, log=log, **kwargs)
        client.session = FakeSession(nas)
        client.base = "https://nas.example.com:5001"
        client.host = "nas.example.com"
        client.verify = verify
        return client

    return make
