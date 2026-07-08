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
import platform
import shutil
import subprocess
import sys
import tarfile
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


def _platform_tag():
    """Short label for the current OS/arch, e.g. win64, macos-arm64, linux-x86_64."""
    if sys.platform.startswith("win"):
        return "win64"
    arch = platform.machine().lower()
    if sys.platform == "darwin":
        return "macos-" + ("arm64" if arch in ("arm64", "aarch64") else "x64")
    return "linux-" + (arch or "x86_64")


def build_exe():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", EXE_NAME,
        "--paths", ROOT,
    ]
    if sys.platform.startswith("win"):
        version_file = os.path.join(ROOT, "version_info.txt")
        write_version_info(version_file)
        cmd += ["--version-file", version_file]
        icon = os.path.join(ROOT, "assets", "icon.ico")
    elif sys.platform == "darwin":
        cmd += ["--osx-bundle-identifier", "com.dynamofoundry.synologysharedownloader"]
        icon = os.path.join(ROOT, "assets", "icon.icns")
    else:  # linux: PyInstaller can't embed an icon into an ELF binary
        icon = None

    if icon and os.path.exists(icon):
        cmd += ["--icon", icon]
    cmd.append(os.path.join(ROOT, "app.py"))

    print(">>", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


DOC_EXTRAS = ["README.md", "LICENSE", "NOTICE", os.path.join("docs", "USAGE.md")]


def make_archive():
    tag = _platform_tag()
    base = "%s-v%s-%s" % (EXE_NAME, __version__, tag)

    if sys.platform == "darwin":
        # Ship the .app bundle; use `ditto` so exec bits / symlinks survive.
        app = os.path.join(DIST, EXE_NAME + ".app")
        if not os.path.isdir(app):
            raise SystemExit("App bundle not found: %s" % app)
        out = os.path.join(DIST, base + ".zip")
        subprocess.check_call(["ditto", "-c", "-k", "--sequesterRsrc",
                               "--keepParent", app, out])
        print("Portable archive:", out)
        return

    exe = os.path.join(DIST, EXE_NAME + (".exe" if sys.platform.startswith("win") else ""))
    if not os.path.exists(exe):
        raise SystemExit("Executable not found: %s" % exe)

    if sys.platform.startswith("win"):
        out = os.path.join(DIST, base + ".zip")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(exe, os.path.basename(exe))
            for rel in DOC_EXTRAS:
                p = os.path.join(ROOT, rel)
                if os.path.exists(p):
                    z.write(p, os.path.basename(rel))
    else:  # linux: tar.gz preserves the executable bit
        out = os.path.join(DIST, base + ".tar.gz")
        with tarfile.open(out, "w:gz") as t:
            t.add(exe, arcname=EXE_NAME)
            for rel in DOC_EXTRAS:
                p = os.path.join(ROOT, rel)
                if os.path.exists(p):
                    t.add(p, arcname=os.path.basename(rel))
    print("Portable archive:", out)


def main():
    if os.path.isdir(DIST):
        shutil.rmtree(DIST, ignore_errors=True)
    build_exe()
    if "--zip" in sys.argv:
        make_archive()
    print("\nDone. Output in:", DIST)


if __name__ == "__main__":
    main()
