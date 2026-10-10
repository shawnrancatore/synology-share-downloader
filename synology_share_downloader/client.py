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

TLS
---
The coordinator and the NAS's QuickConnect ("smartdns") names are reached
with verified HTTPS. Its raw external IP, DDNS name and LAN IP addresses
typically carry the NAS's self-signed certificate, so they are tried without
verification, as a fallback. Connecting that way logs "certificate not
verified for <host>", and login() asks confirm_unverified(host), when given,
before the share password is sent.
"""

import errno
import json
import os
import re
import stat
import time
import urllib.parse
import warnings

import requests
import urllib3

from . import __version__

COORDINATORS = [
    "https://global.quickconnect.to/Serv.php",
    "https://global.quickconnect.cn/Serv.php",
]

# QuickConnect "service id" used by the gofile file-sharing frontend.
FILE_SHARING_ID = "file_sharing_https"

# Opening a .part file never follows a symbolic link, where the OS can refuse
# one, and never truncates: a hard link has to be noticed before a byte changes.
_PART_FLAGS = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
# What open() reports for a symbolic link under O_NOFOLLOW (EMLINK on some BSDs).
_LINK_ERRNOS = (errno.ELOOP, errno.EMLINK)

_SKIP_SYMLINK = "Skipped (symbolic link) %r: the app never writes through a symbolic link or replaces one."
_SKIP_HARD_LINK = ("Skipped (hard link) %r: it has another hard link, "
                   "and the app does not write into a file that does.")


class ShareError(Exception):
    """A user-meaningful error (bad password, unreachable, etc.)."""


class _Skipped:
    """What download_file() returns for a file it refused to write. It is false."""

    def __bool__(self):
        return False

    def __repr__(self):
        return "SKIPPED"


SKIPPED = _Skipped()


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


def _quiet_insecure_warning(host):
    """Silence urllib3's InsecureRequestWarning for this one host only.

    resolve() calls this for each unverified address it tries. It logs the
    one it connects to ("certificate not verified for <host>"), so urllib3's
    warning would repeat it. Warnings about every other host are left as
    they are.
    """
    warnings.filterwarnings(
        "ignore",
        message="Unverified HTTPS request is being made to host '%s'" % re.escape(host),
        category=urllib3.exceptions.InsecureRequestWarning)


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
    created) timestamps so downloaded files keep their original ages.

    Nothing is stamped through a symbolic link, or onto a file that has
    another hard link: either would change a file somewhere else.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return
    if stat.S_ISLNK(st.st_mode) or (stat.S_ISREG(st.st_mode) and st.st_nlink > 1):
        return
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
      http://gofile.me/AbCdE/ExAmPlE123
      https://quickconnect.to/AbCdE/ExAmPlE123
      https://<id>.quickconnect.to/sharing/ExAmPlE123
    """
    url = url.strip()
    if "://" not in url:
        url = "http://" + url
    try:
        p = urllib.parse.urlparse(url)
        host = (p.hostname or "").lower()
    except ValueError:  # its message can quote part of the link
        host, p = "", None
    parts = [seg for seg in p.path.split("/") if seg] if p else []

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


def _hide(text, secret):
    """text with each whole-word occurrence of secret replaced by "…".

    A word may also start right after a percent-escape, as in "%22<id>%22".
    """
    return re.sub(r"(?:(?<![A-Za-z0-9])|(?<=%%[0-9A-Fa-f]{2}))%s(?![A-Za-z0-9])" % re.escape(secret),
                  "…", text)


def _decoded(url):
    """url trimmed, percent-decoded (up to three times), with "\\" read as "/"."""
    text = (url or "").strip()
    for _ in range(3):
        decoded = urllib.parse.unquote(text)
        if decoded == text:
            break
        text = decoded
    return text.replace("\\", "/")


# What redact_share_url() will show: a dotted host name or IPv4 address with
# an optional port, and a first path segment made of letters, digits and "-".
_PLAIN_HOST = re.compile(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+(:[0-9]+)?$")
_PLAIN_SEGMENT = re.compile(r"^[A-Za-z0-9-]+$")


def redact_share_url(url):
    """The share link as it may appear in a log, without the share's id.

    Only the scheme, the host and the first path segment are kept, and only
    when another segment follows: "http://gofile.me/AbCdE/ExAmPlE123" becomes
    "http://gofile.me/AbCdE/…". Everything after that is replaced by "…".
    A lone segment is the id itself, so "gofile.me/ExAmPlE123" becomes
    "gofile.me/…".

    The link is percent-decoded first (up to three times), a backslash counts
    as a "/", and a user name is dropped. Anything that is not a plain host
    and path, such as a bare id or text that does not parse, becomes "…".
    The id parse_share_url() reads from the link is also removed from the
    result, wherever it appears.
    """
    text = _decoded(url)
    has_scheme = "://" in text
    try:
        parts = urllib.parse.urlsplit(text if has_scheme else "//" + text)
    except ValueError:
        return "…"
    host = parts.netloc.rpartition("@")[2]
    if not _PLAIN_HOST.match(host) or (has_scheme and parts.scheme not in ("http", "https")):
        return "…"
    out = (parts.scheme + "://" if has_scheme else "") + host
    segs = [seg for seg in parts.path.split("/") if seg]
    if len(segs) >= 2 and _PLAIN_SEGMENT.match(segs[0]):
        out += "/" + segs[0]
    if segs:
        out += "/…"
    try:
        link_id = parse_share_url(text)[1]
    except ShareError:
        link_id = None
    return _hide(out, link_id) if link_id else out


_WORD = re.compile(r"[A-Za-z0-9]+")


def hide_share_link(text, url):
    """text, safe to log: nothing of the share link url beyond its redacted form.

    The link itself is replaced by redact_share_url(url). Then every word of
    the link, as pasted and at each level of percent-decoding, that the
    redacted form does not show is replaced by "…". So an error message that
    quotes part of the link cannot carry the share's id.
    """
    raw = (url or "").strip()
    shown = redact_share_url(raw)
    text = str(text)
    if raw:
        text = text.replace(raw, shown)
    words, form = set(), raw.replace("\\", "/")
    for _ in range(10):
        words.update(_WORD.findall(form))
        decoded = urllib.parse.unquote(form)
        if decoded == form:
            break
        form = decoded
    for word in sorted(words - set(_WORD.findall(shown)), key=len, reverse=True):
        text = _hide(text, word)
    return text


class SynoShareClient:
    """One share: resolve() it, login(), then list and download.

    log(msg) receives progress messages. confirm_unverified(host) -> bool is
    called by login() before the share password is sent over a connection
    whose certificate was not verified; returning False stops the login.
    verify_tls is only the starting value: resolve() sets self.verify for the
    address it connects to.
    """

    def __init__(self, share_url, password, log=None, verify_tls=True,
                 confirm_unverified=None):
        self.share_url = share_url
        self.password = password
        self._log = log or (lambda *_: None)
        self._confirm_unverified = confirm_unverified
        self.qc_id, self.link_id, self.is_gofile = parse_share_url(share_url)
        if not self.link_id:
            raise ShareError("Could not read the share id from the link.")
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "SynologyShareDownloader/%s" % __version__
        self.base = None           # e.g. https://host:53748
        self.host = None           # the host part of base
        self.verify = verify_tls   # per-connection TLS verification
        self.root_path = None      # e.g. /mounted
        self.is_folder = True

    # ---- low level -------------------------------------------------------
    def scrub(self, text):
        """text with the share's id replaced by "…", for logs and error messages.

        Request errors can quote the URL, and download URLs carry the id as
        _sharing_id=%22<id>%22. A bare id is replaced only as a whole word, so
        a short id does not garble the rest of the message.
        """
        quoted = json.dumps(self.link_id)
        text = str(text)
        for form in (urllib.parse.quote_plus(quoted), quoted):
            text = text.replace(form, "…")
        return hide_share_link(_hide(text, self.link_id), self.share_url)

    def _refuse_links(self, local_path, part):
        """Log and return True if a link means this file must be skipped.

        A symbolic link at local_path or at its .part file would be written
        through or replaced. A .part file with another hard link shares its
        contents with a file somewhere else.
        """
        for path in (local_path, part):
            if os.path.islink(path):
                self._log(_SKIP_SYMLINK % path)
                return True
        try:
            shared = os.lstat(part).st_nlink > 1
        except OSError:
            shared = False
        if shared:
            self._log(_SKIP_HARD_LINK % part)
        return shared

    def _open_part(self, part, resume):
        """Open the .part file for writing, or log why not and return None."""
        try:
            fd = os.open(part, _PART_FLAGS | (os.O_APPEND if resume else 0), 0o666)
        except OSError as e:
            if e.errno in _LINK_ERRNOS:
                self._log(_SKIP_SYMLINK % part)
                return None
            raise
        try:
            if os.fstat(fd).st_nlink <= 1:
                if not resume:
                    os.ftruncate(fd, 0)
                return os.fdopen(fd, "ab" if resume else "wb")
        except BaseException:
            os.close(fd)
            raise
        os.close(fd)
        self._log(_SKIP_HARD_LINK % part)
        return None

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
            raise ShareError("Could not locate the Synology server for that link.\n(%s)"
                             % self.scrub(last_err))

        self._server_info = info
        candidates = self._candidates(info)
        self._log("Resolved server. Trying %d address(es)..." % len(candidates))
        for host, port, verify, label in candidates:
            base = "https://%s:%s" % (host, port)
            if not verify:
                _quiet_insecure_warning(host)  # if used, the log line below says so
            if self._probe(base, verify):
                self.base = base
                self.host = host
                self.verify = verify
                self._log("Connected via %s (%s:%s)." % (label, host, port))
                if not verify:
                    self._log("Warning: certificate not verified for %s. "
                              "The app cannot confirm this is your NAS." % host)
                return
        raise ShareError(
            "Found the server but couldn't reach it from this network.\n"
            "The NAS may be offline, or its remote-access port isn't open."
        )

    def _candidates(self, info):
        """(host, port, verify, label) for each address to try, in order.

        Only QuickConnect's own names are verified; the rest are a fallback.
        """
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
        if not self.verify and self._confirm_unverified is not None \
                and not self._confirm_unverified(self.host):
            raise ShareError("Not connected. The share password was not sent, because "
                             "the certificate for %s could not be verified." % self.host)
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

    def walk(self, folder_path, stop=None):
        """Yield every entry (folders and files) recursively (depth-first)."""
        stack = [folder_path]
        while stack:
            if stop and stop():
                return
            cur = stack.pop()
            for e in self.list_folder(cur):
                if stop and stop():
                    return
                yield e
                if e["isdir"]:
                    stack.append(e["path"])

    def walk_files(self, folder_path, stop=None):
        """Yield file entries recursively under folder_path (depth-first)."""
        for e in self.walk(folder_path, stop=stop):
            if not e["isdir"]:
                yield e

    # ---- step 4: download (resumable) ------------------------------------
    def download_file(self, remote_path, local_path, expected_size=None,
                      progress=None, stop=None, retries=5,
                      mtime=None, crtime=None):
        """Download one file to local_path, resuming a .part file if present.

        progress(bytes_done, total_or_None) is called periodically.
        stop() -> True aborts. Returns True if completed, False if stopped,
        and SKIPPED (which is also false) if the file was refused because of
        a link. mtime/crtime (Unix epoch) are stamped onto the finished file
        so it keeps its original age.

        The file is skipped, with a "Skipped (...)" log line, if local_path
        or its .part file is a symbolic link, or if the .part file has
        another hard link. This is checked before each attempt, again on the
        open file, and before the finished file is moved into place.
        """
        part = local_path + ".part"
        if self._refuse_links(local_path, part):
            return SKIPPED
        if expected_size is not None and os.path.exists(local_path) and \
                os.path.getsize(local_path) == expected_size:
            apply_file_times(local_path, mtime, crtime)
            if progress:
                progress(expected_size, expected_size)
            return True

        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

        attempt = 0
        while True:
            attempt += 1
            if attempt > 1 and self._refuse_links(local_path, part):
                return SKIPPED
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
                    if self._refuse_links(local_path, part):
                        return SKIPPED
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

                fh = self._open_part(part, bool(have))
                if fh is None:
                    r.close()
                    return SKIPPED
                done = have
                with fh:
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
                if self._refuse_links(local_path, part):
                    return SKIPPED
                os.replace(part, local_path)
                apply_file_times(local_path, mtime, crtime)
                return True

            except ShareError:
                raise
            except Exception as e:
                if isinstance(e, OSError) and e.errno in _LINK_ERRNOS:
                    self._log(_SKIP_SYMLINK % part)
                    return SKIPPED
                if stop and stop():
                    return False
                if attempt >= retries:
                    raise ShareError("Failed after %d attempts: %s" % (retries, self.scrub(e)))
                wait = min(2 ** attempt, 15)
                self._log("  retry %d/%d in %ds (%s)" % (attempt, retries, wait, self.scrub(e)))
                time.sleep(wait)
