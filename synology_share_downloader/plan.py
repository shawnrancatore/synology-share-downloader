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
"""Turn a selection on the share into the local files and folders to write.

Every name in a listing comes from the server, so it is untrusted. A path is
only used if it stays inside the destination folder on Windows, macOS and
Linux alike; anything else is skipped and logged.
"""

import os
import re
from dataclasses import dataclass, field

_DRIVE = re.compile(r"^[A-Za-z]:")


class UnsafePathError(ValueError):
    """A server-supplied path that would land outside the destination."""


def _part_problem(part):
    """Why one path component is unsafe on some OS, or None if it is fine."""
    if part == "":
        return "it is an absolute path or has an empty part"
    if "\x00" in part:
        return "it contains a NUL character"
    if "\\" in part:
        return "it contains a backslash, which Windows reads as a folder separator"
    if _DRIVE.match(part):
        return "it starts with a drive letter"
    if part.strip(". ") == "":
        # ".", "..", and spellings Windows trims down to them, such as ".. "
        return "it has a '.' or '..' part"
    return None


def _inside(path, root):
    try:
        common = os.path.commonpath([root, path])
    except ValueError:  # different drives on Windows
        return False
    return os.path.normcase(common) == os.path.normcase(root)


def safe_local_path(dest, remote_path, remote_base):
    """Return where remote_path goes under dest, or raise UnsafePathError.

    remote_path must lie under remote_base (Synology paths use "/", for
    example "/share/photos/a.jpg" under "/share"). The part below remote_base
    is mirrored below dest. The result must also resolve inside dest after
    following any links that already exist on disk.
    """
    prefix = remote_base.rstrip("/") + "/"
    if not remote_path.startswith(prefix):
        raise UnsafePathError("it is not inside the folder being downloaded")
    parts = remote_path[len(prefix):].split("/")
    for part in parts:
        problem = _part_problem(part)
        if problem:
            raise UnsafePathError(problem)
    local = os.path.join(dest, *parts)
    root = os.path.realpath(dest)
    if not _inside(os.path.realpath(local), root):
        raise UnsafePathError("it leads outside the destination folder through a link")
    if not _inside(os.path.realpath(local + ".part"), root):
        raise UnsafePathError("its .part file is a link that leads outside the destination folder")
    return local


@dataclass
class DownloadPlan:
    files: list = field(default_factory=list)    # (remote, local, size, mtime, crtime)
    folders: list = field(default_factory=list)  # (local, mtime, crtime)
    skipped: list = field(default_factory=list)  # (remote, reason)
    total_bytes: int = 0


def plan_downloads(client, picks, dest, log=None, stop=None, progress=None):
    """Walk the picked items on the share and plan where each one goes.

    picks are dicts with path, isdir, size and, optionally, mtime and crtime.
    Each pick lands in dest under its own name, with its folders mirrored
    below it. Unsafe names are skipped (and logged); a skipped folder is not
    listed at all. progress(files, total_bytes) is called every 200 entries.
    """
    log = log or (lambda _msg: None)
    stop = stop or (lambda: False)
    plan = DownloadPlan()
    scanned = 0

    def skip(remote_path, reason):
        plan.skipped.append((remote_path, reason))
        log("Skipped %r: %s." % (remote_path, reason))

    def place(remote_path, remote_base):
        try:
            return safe_local_path(dest, remote_path, remote_base)
        except UnsafePathError as e:
            skip(remote_path, str(e))
            return None

    for pick in picks:
        if stop():
            break
        pick_path = pick["path"]
        base = pick_path.rsplit("/", 1)[0]
        local = place(pick_path, base)
        if local is None:
            continue
        if not pick["isdir"]:
            plan.files.append((pick_path, local, pick["size"],
                               pick.get("mtime"), pick.get("crtime")))
            plan.total_bytes += pick["size"]
            continue
        plan.folders.append((local, pick.get("mtime"), pick.get("crtime")))
        stack = [pick_path]
        while stack and not stop():
            for e in client.list_folder(stack.pop()):
                if stop():
                    break
                scanned += 1
                if not e["path"].startswith(pick_path + "/"):
                    skip(e["path"], "it is not inside the folder being downloaded")
                    continue
                local = place(e["path"], base)
                if local is None:
                    continue
                if e["isdir"]:
                    plan.folders.append((local, e.get("mtime"), e.get("crtime")))
                    stack.append(e["path"])
                else:
                    plan.files.append((e["path"], local, e["size"],
                                       e.get("mtime"), e.get("crtime")))
                    plan.total_bytes += e["size"]
                if progress and scanned % 200 == 0:
                    progress(len(plan.files), plan.total_bytes)
    return plan
