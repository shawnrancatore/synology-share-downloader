# Copyright 2026 Dynamo Foundry LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Network client for downloading files from a Synology "gofile.me" (QuickConnect)
folder-share link, one file at a time, with resumable HTTP-Range downloads.

No Synology account is needed -- only the public share URL and its password.

Protocol
--------
  1. Resolve the gofile.me / quickconnect.to id via the QuickConnect coordinator
     (global.quickconnect.to/Serv.php) to get the NAS's reachable address(es).
  2. POST SYNO.Core.Sharing.Login with the share password -> sets `sharing_sid`.
  3. GET SYNO.Core.Sharing.Initdata (needs header `X-SYNO-SHARING: <link id>`)
     -> the share's virtual root folder name (Private.filename, e.g. "mounted").
  4. List folders with SYNO.FolderSharing.List (folder_path="/<root>").
  5. Download files with SYNO.FolderSharing.Download (supports Range -> resume).
"""

import json
import os
import time
import urllib.parse

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

COORDINATORS = [
    "https://global.quickconnect.to/Serv.php",
    "https://global.quickconnect.cn/Serv.php",
]

# QuickConnect "service id" used by the gofile file-sharing frontend.
FILE_SHARING_ID = "file_sharing_https"


class ShareError(Exception):
    """A user-meaningful error (bad password, unreachable, etc.)."""


# Synology WebAPI error codes we translate to friendly text.
_ERR = {
    1001: "Wrong share password.",
    119: "Session expired -- please reconnect.",
    126: "The share did not grant permission for this request.",
    407: "No such file or folder on the share.",
    408: "No such file or folder on the share.",
}


def _api_error(code):
    return _ERR.get(code, "Synology API error code %s." % code)


def _set_windows_ctime(path, ctime_epoch):
    """Best-effort: set a file's Windows 'creation time' from a Unix epoch."""
    if os.name != "nt" or not ctime_epoch:
        return
    try:
        import ctypes
        from ctypes import wintypes
        ts = int((ctime_epoch + 11644473600) * 10_000_000)  # -> 100ns since 1601
        ft = wintypes.FILETIME(ts & 0xFFFFFFFF, (ts >> 32) & 0xFFFFFFFF)
        k32 = ctypes.windll.kernel32
        FILE_WRITE_ATTRIBUTES = 0x100
        OPEN_EXISTING = 3
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
        handle = k32.CreateFileW(path, FILE_WRITE_ATTRIBUTES, 0, None,
                                 OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None)
        if handle in (-1, 0, 0xFFFFFFFFFFFFFFFF):
            return
        try:
            k32.SetFileTime(handle, ctypes.byref(ft), None, None)
        finally:
            k32.CloseHandle(handle)
    except Exception:
        pass


def apply_file_times(path, mtime=None, crtime=None):
    """Stamp the local file with the share's modified (and, on Windows,
    created) timestamps so downloaded files keep their original ages."""
    if mtime:
        try:
            os.utime(path, (mtime, mtime))
        except OSError:
            pass
    if crtime:
        _set_windows_ctime(path, crtime)


def parse_share_url(url):
    """Return (quickconnect_id, link_id, is_gofile) from a share URL.

    Accepts forms like:
      http://gofile.me/75lxK/7vqFT49uA
      https://quickconnect.to/75lxK/7vqFT49uA
      https://<id>.quickconnect.to/sharing/7vqFT49uA
    """
    url = url.strip()
    if "://" not in url:
        url = "http://" + url
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()
    parts = [seg for seg in p.path.split("/") if seg]

    is_gofile = host.endswith("gofile.me")

    if host.endswith("gofile.me") or host.endswith("quickconnect.to") or host.endswith("quickconnect.cn"):
        sub = host.split(".")[0]
        if host.endswith("gofile.me") or host in ("quickconnect.to", "quickconnect.cn",
                                                  "global.quickconnect.to", "global.quickconnect.cn"):
            # .../<qc_id>/<link_id>
            if len(parts) >= 2 and parts[0] != "sharing":
                return parts[0], parts[-1], is_gofile
            if len(parts) >= 1:
                return None, parts[-1], is_gofile
        else:
            # <qc_id>.quickconnect.to/sharing/<link_id>
            link = parts[-1] if parts else None
            return sub, link, is_gofile

    raise ShareError(
        "That doesn't look like a Synology share link.\n"
        "Expected something like: http://gofile.me/XXXXX/YYYYYYYYY"
    )


class SynoShareClient:
    def __init__(self, share_url, password, log=None, verify_tls=True):
        self.share_url = share_url
        self.password = password
        self._log = log or (lambda *_: None)
        self.qc_id, self.link_id, self.is_gofile = parse_share_url(share_url)
        if not self.link_id:
            raise ShareError("Could not read the share id from the link.")
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "SynologyShareDownloader/1.0"
        self.base = None           # e.g. https://host:53748
        self.verify = verify_tls   # per-connection TLS verification
        self.root_path = None      # e.g. /mounted
        self.is_folder = True

    # ---- low level -------------------------------------------------------
    def _entry_url(self):
        return self.base + "/sharing/webapi/entry.cgi"

    def _sharing_headers(self):
        return {"X-SYNO-SHARING": self.link_id}

    def _call(self, data, stream=False, extra_headers=None, method="POST",
              timeout=30):
        headers = self._sharing_headers()
        if extra_headers:
            headers.update(extra_headers)
        if method == "POST":
            return self.session.post(self._entry_url(), data=data, headers=headers,
                                     verify=self.verify, timeout=timeout, stream=stream)
        return self.session.get(self._entry_url(), params=data, headers=headers,
                                verify=self.verify, timeout=timeout, stream=stream)

    # ---- step 1: resolve -------------------------------------------------
    def resolve(self):
        """Resolve the QuickConnect id -> pick a reachable base URL."""
        if not self.qc_id:
            raise ShareError("The link is missing the server id.")
        info = None
        last_err = None
        for coord in COORDINATORS:
            try:
                body = [{
                    "version": 1,
                    "command": "get_server_info",
                    "stop_when_error": False,
                    "stop_when_success": False,
                    "id": FILE_SHARING_ID,
                    "serverID": self.qc_id,
                    "is_gofile": bool(self.is_gofile),
                    "path": self.link_id,
                }]
                resp = requests.post(coord, data=json.dumps(body), timeout=15)
                j = resp.json()
                obj = j[0] if isinstance(j, list) else j
                if obj.get("errno", 0) == 0 and "server" in obj:
                    info = obj
                    break
                last_err = obj.get("errinfo") or ("errno %s" % obj.get("errno"))
            except Exception as e:  # network / json
                last_err = str(e)
        if not info:
            raise ShareError("Could not locate the Synology server for that link.\n(%s)" % last_err)

        self._server_info = info
        candidates = self._candidates(info)
        self._log("Resolved server. Trying %d address(es)..." % len(candidates))
        for host, port, verify, label in candidates:
            base = "https://%s:%s" % (host, port)
            if self._probe(base, verify):
                self.base = base
                self.verify = verify
                self._log("Connected via %s (%s:%s)" % (label, host, port))
                return
        raise ShareError(
            "Found the server but couldn't reach it from this network.\n"
            "The NAS may be offline, or its remote-access port isn't open."
        )

    def _candidates(self, info):
        srv = info.get("server", {})
        svc = info.get("service", {})
        sdns = info.get("smartdns", {})
        ext_port = svc.get("ext_port") or 0
        int_port = svc.get("port") or 5001
        out = []
        # 1) smartdns external host (valid TLS cert), external port
        if sdns.get("external") and ext_port:
            out.append((sdns["external"], ext_port, True, "direct (secure name)"))
        # 2) raw external IP, external port (cert won't match -> no verify)
        ext = srv.get("external", {})
        if ext.get("ip") and ext_port:
            out.append((ext["ip"], ext_port, False, "direct IP"))
        # 3) DDNS name on internal / external port (if user forwarded a port)
        if srv.get("ddns") and srv.get("ddns") != "NULL":
            out.append((srv["ddns"], int_port, False, "DDNS"))
            if ext_port:
                out.append((srv["ddns"], ext_port, False, "DDNS"))
        # 4) LAN hosts (only useful on the same network)
        for lan in sdns.get("lan", []) or []:
            out.append((lan, int_port, True, "LAN"))
        for iface in srv.get("interface", []) or []:
            if iface.get("ip"):
                out.append((iface["ip"], int_port, False, "LAN IP"))
        return out

    def _probe(self, base, verify):
        url = base + "/webapi/query.cgi"
        try:
            r = requests.get(url, params={
                "api": "SYNO.API.Info", "version": 1, "method": "query",
                "query": "SYNO.API.Info",
            }, verify=verify, timeout=5)
            return r.ok and r.json().get("success") is True
        except Exception:
            return False

    # ---- step 2: login ---------------------------------------------------
    def login(self):
        r = self.session.post(self._entry_url(), data={
            "api": "SYNO.Core.Sharing.Login", "version": 1, "method": "login",
            "sharing_id": self.link_id, "password": self.password,
        }, verify=self.verify, timeout=20)
        j = r.json()
        if not j.get("success"):
            code = (j.get("error") or {}).get("code")
            if code == 1001:
                raise ShareError("Wrong share password.")
            raise ShareError("Login failed (%s)." % _api_error(code))
        # sharing_sid cookie now stored in the session.
        self._discover_root()

    def _discover_root(self):
        r = self._call({
            "api": "SYNO.Core.Sharing.Initdata", "version": 1, "method": "get",
        }, timeout=25)
        j = r.json()
        if not j.get("success"):
            raise ShareError("Could not read the share (%s)." %
                             _api_error((j.get("error") or {}).get("code")))
        data = j.get("data", {})
        sharing = data.get("Sharing", {})
        self.is_folder = bool(sharing.get("app", {}).get("is_folder", True))
        name = (data.get("Private") or {}).get("filename")
        if not name:
            raise ShareError("This share doesn't expose a browsable folder.")
        self.root_path = "/" + name
        self._log("Share opened. Root folder: %s" % self.root_path)

    # ---- step 3: list ----------------------------------------------------
    def list_folder(self, folder_path):
        """Return a list of entries: dicts with name, path, isdir, size."""
        entries = []
        offset = 0
        limit = 1000
        while True:
            r = self._call({
                "api": "SYNO.FolderSharing.List", "version": 2, "method": "list",
                "offset": offset, "limit": limit,
                "sort_by": '"name"', "sort_direction": '"ASC"',
                "action": '"enum"', "filetype": '"all"',
                "additional": json.dumps(["size", "time", "type"]),
                "folder_path": json.dumps(folder_path),
                "_sharing_id": json.dumps(self.link_id),
            }, timeout=60)
            j = r.json()
            if not j.get("success"):
                raise ShareError("Could not list '%s' (%s)." %
                                 (folder_path, _api_error((j.get("error") or {}).get("code"))))
            data = j.get("data", {})
            files = data.get("files", [])
            for f in files:
                add = f.get("additional") or {}
                t = add.get("time") or {}
                entries.append({
                    "name": f.get("name"),
                    "path": f.get("path"),
                    "isdir": bool(f.get("isdir")),
                    "size": add.get("size", 0) or 0,
                    "mtime": t.get("mtime"),
                    "crtime": t.get("crtime"),
                })
            total = data.get("total", len(entries))
            offset += len(files)
            if not files or offset >= total:
                break
        return entries

    def walk_files(self, folder_path, stop=None):
        """Yield file entries recursively under folder_path (depth-first)."""
        stack = [folder_path]
        while stack:
            if stop and stop():
                return
            cur = stack.pop()
            for e in self.list_folder(cur):
                if stop and stop():
                    return
                if e["isdir"]:
                    stack.append(e["path"])
                else:
                    yield e

    # ---- step 4: download (resumable) ------------------------------------
    def download_file(self, remote_path, local_path, expected_size=None,
                      progress=None, stop=None, retries=5,
                      mtime=None, crtime=None):
        """Download one file to local_path, resuming a .part file if present.

        progress(bytes_done, total_or_None) is called periodically.
        stop() -> True aborts. Returns True if completed, False if stopped.
        mtime/crtime (Unix epoch) are stamped onto the finished file so it
        keeps its original age.
        """
        if expected_size is not None and os.path.exists(local_path) and \
                os.path.getsize(local_path) == expected_size:
            apply_file_times(local_path, mtime, crtime)
            if progress:
                progress(expected_size, expected_size)
            return True

        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        part = local_path + ".part"

        attempt = 0
        while True:
            attempt += 1
            have = os.path.getsize(part) if os.path.exists(part) else 0
            headers = {}
            if have:
                headers["Range"] = "bytes=%d-" % have
            try:
                r = self._call({
                    "api": "SYNO.FolderSharing.Download", "version": 2,
                    "method": "download", "mode": '"download"',
                    "_sharing_id": json.dumps(self.link_id),
                    "path": json.dumps([remote_path]),
                }, stream=True, extra_headers=headers, method="GET", timeout=60)

                if r.status_code == 416:  # range not satisfiable -> already complete
                    r.close()
                    if os.path.exists(part):
                        os.replace(part, local_path)
                    apply_file_times(local_path, mtime, crtime)
                    if progress and expected_size is not None:
                        progress(expected_size, expected_size)
                    return True

                if have and r.status_code != 206:
                    # Server ignored our Range: restart from scratch.
                    have = 0
                    if os.path.exists(part):
                        os.remove(part)

                ctype = r.headers.get("Content-Type", "")
                if "application/json" in ctype:
                    msg = ""
                    try:
                        msg = _api_error((r.json().get("error") or {}).get("code"))
                    except Exception:
                        pass
                    r.close()
                    raise ShareError("Download refused: %s" % (msg or "server error"))

                total = None
                clen = r.headers.get("Content-Length")
                if clen is not None:
                    total = have + int(clen)
                if expected_size is not None:
                    total = expected_size

                mode = "ab" if have else "wb"
                done = have
                with open(part, mode) as fh:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if stop and stop():
                            r.close()
                            return False
                        if chunk:
                            fh.write(chunk)
                            done += len(chunk)
                            if progress:
                                progress(done, total)
                r.close()

                final_size = os.path.getsize(part)
                if expected_size is not None and final_size != expected_size:
                    raise IOError("size mismatch: got %d, expected %d" %
                                  (final_size, expected_size))
                os.replace(part, local_path)
                apply_file_times(local_path, mtime, crtime)
                return True

            except ShareError:
                raise
            except Exception as e:
                if stop and stop():
                    return False
                if attempt >= retries:
                    raise ShareError("Failed after %d attempts: %s" % (retries, e))
                wait = min(2 ** attempt, 15)
                self._log("  retry %d/%d in %ds (%s)" % (attempt, retries, wait, e))
                time.sleep(wait)
