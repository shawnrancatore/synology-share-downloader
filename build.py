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
Build a single, portable Windows .exe with PyInstaller, and (optionally) a
portable release .zip.

Usage:
    python build.py            # build dist/SynologyShareDownloader.exe
    python build.py --zip      # also produce dist/<name>-v<ver>-win64.zip
"""

import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from synology_share_downloader import APP_NAME, COMPANY, COPYRIGHT, __version__  # noqa: E402

EXE_NAME = "SynologyShareDownloader"
DIST = os.path.join(ROOT, "dist")


def _version_tuple():
    parts = (list(map(int, __version__.split("."))) + [0, 0, 0, 0])[:4]
    return tuple(parts)


def write_version_info(path):
    v = _version_tuple()
    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={v}, prodvers={v},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', {COMPANY!r}),
        StringStruct('FileDescription', {APP_NAME!r}),
        StringStruct('FileVersion', {__version__!r}),
        StringStruct('InternalName', {EXE_NAME!r}),
        StringStruct('LegalCopyright', {COPYRIGHT!r}),
        StringStruct('OriginalFilename', {EXE_NAME + '.exe'!r}),
        StringStruct('ProductName', {APP_NAME!r}),
        StringStruct('ProductVersion', {__version__!r})])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def build_exe():
    version_file = os.path.join(ROOT, "version_info.txt")
    write_version_info(version_file)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", EXE_NAME,
        "--paths", ROOT,
    ]
    if os.name == "nt":
        cmd += ["--version-file", version_file]
    icon = os.path.join(ROOT, "assets", "icon.ico")
    if os.path.exists(icon):
        cmd += ["--icon", icon]
    cmd.append(os.path.join(ROOT, "app.py"))

    print(">>", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def make_zip():
    exe = os.path.join(DIST, EXE_NAME + (".exe" if os.name == "nt" else ""))
    if not os.path.exists(exe):
        raise SystemExit("Executable not found: %s" % exe)
    plat = "win64" if os.name == "nt" else sys.platform
    zip_path = os.path.join(DIST, "%s-v%s-%s.zip" % (EXE_NAME, __version__, plat))
    extras = ["README.md", "LICENSE", "NOTICE", os.path.join("docs", "USAGE.md")]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe, os.path.basename(exe))
        for rel in extras:
            p = os.path.join(ROOT, rel)
            if os.path.exists(p):
                z.write(p, os.path.basename(rel))
    print("Portable zip:", zip_path)


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST, ignore_errors=True)
    build_exe()
    if "--zip" in sys.argv:
        make_zip()
    print("\nDone. Output in:", DIST)


if __name__ == "__main__":
    main()
