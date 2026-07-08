<img src="assets/icon.png" width="88" align="right" alt="app icon">

# Synology Share Downloader

[![Release](https://img.shields.io/github/v/release/shawnrancatore/synology-share-downloader?sort=semver)](https://github.com/shawnrancatore/synology-share-downloader/releases)
[![CI](https://github.com/shawnrancatore/synology-share-downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/shawnrancatore/synology-share-downloader/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-0078D6)](https://github.com/shawnrancatore/synology-share-downloader/releases)

<img width="1291" height="1038" alt="image" src="https://github.com/user-attachments/assets/0d5b2b76-5f66-4584-9c84-0c6b26488825" />

**Download every file from a Synology share link — one file at a time, with
resume — instead of squashing the whole folder into one giant ZIP.**

Synology's *"Download Folder"* button on a shared link bundles everything into a
single ZIP. That's painful for large folders: no resume, no progress, and one
network blip means starting over. This little Windows app browses the shared
folder and downloads the files individually, keeping the folder structure **and
the original file dates**, and it can pick up right where it left off.

No Synology account required — just the public share link and its password.
Nothing to install for the person running it — it's a single portable app for
**Windows, macOS, and Linux**.

> Works with the `http://gofile.me/XXXXX/YYYYYYYYY` style links (Synology
> QuickConnect shared folders).

---

## Features

- 🗂️ **Browse the share** in a folder tree and pick exactly what you want.
- 📥 **Download the entire share** in one click — with a total-size warning first.
- 🚀 **Parallel downloads** (1–8 at once, configurable) for real speed.
- ⬇️ **File-by-file downloads** — no forced ZIP.
- ⏯️ **Resumable** — interrupted downloads continue via HTTP Range; finished
  files are skipped on re-run.
- 🕒 **Preserves dates** — original modified time (and creation time on Windows)
  on both **files and folders**, so everything keeps its familiar age. Empty
  folders are recreated too.
- 🌲 **Keeps the folder structure** under a destination you choose.
- 📊 **Live progress** — per-file and overall, with speed and ETA.
- 📦 **Portable** — a single app for **Windows, macOS, and Linux**, no installer,
  no Python needed to run it.

## Download & run (for end users)

Grab the build for your OS from the
[**Releases**](https://github.com/shawnrancatore/synology-share-downloader/releases)
page:

| OS | Download | Run |
|----|----------|-----|
| **Windows** | `…-win64.zip` (or the bare `.exe`) | Unzip, double-click `SynologyShareDownloader.exe` |
| **macOS** | `…-macos-arm64.zip` | Unzip, drag `SynologyShareDownloader.app` to Applications, open it |
| **Linux** | `…-linux-x86_64.tar.gz` | `tar xzf …tar.gz` then `./SynologyShareDownloader` |

Then paste the share link + password → **Connect**, pick folders/files, choose a
destination, and click **Download selected**.

📖 **Full step-by-step guide:** [docs/USAGE.md](docs/USAGE.md)

> **First-run security prompts** (the app isn't code-signed):
> - **Windows:** SmartScreen → **More info → Run anyway**.
> - **macOS:** right-click the app → **Open** → **Open** (or *System Settings →
>   Privacy & Security → Open Anyway*).
> - **Linux:** make it executable if needed — `chmod +x SynologyShareDownloader`.
>
> Or build it yourself (below).

## How it works

The `gofile.me` link is a QuickConnect redirector. The app:

1. Resolves the QuickConnect id to the NAS's reachable address.
2. Logs in to the share with its password.
3. Lists folders/files via Synology's `FolderSharing` WebAPI.
4. Downloads each file with HTTP Range requests (which is what makes resuming
   possible).

See [`synology_share_downloader/client.py`](synology_share_downloader/client.py)
— it's usable as a standalone library for scripting, too.

## Build from source

Requirements: **Python 3.9+** (Windows, macOS, or Linux). PyInstaller builds for
the OS it runs on, so build on each platform you want to ship.

```bash
pip install -r requirements.txt pyinstaller
python build.py --zip
```

Output lands in `dist/` — the portable app plus an archive for the current OS
(`…-win64.zip`, `…-macos-*.zip` containing the `.app`, or `…-linux-*.tar.gz`).

To run from source without building:

```bash
pip install -r requirements.txt
python app.py            # or:  python -m synology_share_downloader
```

Releases are built automatically by GitHub Actions when a `v*` tag is pushed
(see [`.github/workflows/release.yml`](.github/workflows/release.yml)).

## Contributing

Contributions are very welcome — this project is meant to be a single place the
community rallies around rather than fragmenting into forks. Please:

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the
   [Code of Conduct](CODE_OF_CONDUCT.md).
2. Open an [issue](https://github.com/shawnrancatore/synology-share-downloader/issues)
   to discuss a bug or feature before large changes.
3. Fork, branch, and open a pull request. Keep PRs focused, run the tests
   (`pytest`) and linter (`ruff check .`), and describe the change clearly.

Good first contributions: macOS/Linux release builds, localization, a
drag-and-drop target for share links, an in-app update check, or code-signing
the Windows build.

## License

Licensed under the **Apache License, Version 2.0** — see [LICENSE](LICENSE) and
[NOTICE](NOTICE). You're free to use, modify, and redistribute it, including in
commercial settings, provided you keep the notices.

© 2026 **Dynamo Foundry LLC** — *a Software Company.*

*Not affiliated with Synology Inc. "Synology" and "QuickConnect" are trademarks
of Synology Inc., referenced here only to describe interoperability.*
