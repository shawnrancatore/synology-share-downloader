# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] — 2026-07-08

### Security
- Releases now ship a **`SHA256SUMS.txt`** and a **build-provenance attestation**
  for every binary, so downloads can be verified (`gh attestation verify …`) and
  checked for tampering. The apps remain unsigned; the README explains how to
  verify them and how code signing can be added to remove the first-run prompt.

## [1.2.0] — 2026-07-08

### Added
- **macOS and Linux support.** Official portable release builds are now produced
  for Windows (`.exe`/zip), macOS (`.app` in a zip), and Linux (`tar.gz`), built
  in a 3-OS GitHub Actions matrix. A macOS `.icns` icon was added.

### Changed
- The GUI now picks the native `ttk` theme per platform and uses a portable
  monospace font, so it looks at home on all three systems.
- CI now runs on Windows, macOS, and Linux.

## [1.1.0] — 2026-07-07

### Added
- **Download entire share** button — scans the share and shows a total
  file-count/size confirmation (with a warning for very large downloads) before
  starting.
- **Parallel downloads** — download 1–8 files concurrently (configurable, default
  4) for substantially faster transfers.
- **Application icon** — a proper icon for the window and the `.exe`.

## [1.0.2] — 2026-07-07

### Added
- **Folder dates are now preserved too** — downloaded folders get their original
  modified time (and creation time on Windows), applied after their contents are
  written so the dates stick. Empty folders from the share are recreated as well.

## [1.0.1] — 2026-07-07

Maintenance release — no changes to the application itself.

### Changed
- CI/build only: upgraded GitHub Actions to their Node.js 24 majors
  (`checkout@v5`, `setup-python@v6`, `upload-artifact@v6`,
  `action-gh-release@v3`) to clear Node.js 20 deprecation warnings.
- Fixed the test import path so the suite runs under bare `pytest` in CI.

## [1.0.0] — 2026-07-07

Initial public release.

### Added
- Browse a Synology folder-share link (`gofile.me` / QuickConnect) in a folder
  tree and select folders or individual files to download.
- File-by-file downloading — no forced ZIP of the whole folder.
- **Resumable** downloads via HTTP Range; already-complete files are skipped on
  re-run and partial files continue from where they stopped.
- **Preserves original file timestamps** — modified time on all platforms, and
  creation time on Windows.
- Preserves the shared folder's directory structure under a chosen destination.
- Live per-file and overall progress with transfer speed and ETA.
- Automatic connection strategy (secure QuickConnect name → direct IP → DDNS →
  LAN).
- Help menu with **About** dialog (version, license, project link) and a link to
  the documentation.
- Single portable Windows `.exe` build via PyInstaller, plus a portable release
  `.zip`, produced automatically on tagged releases.

[1.2.1]: https://github.com/shawnrancatore/synology-share-downloader/releases/tag/v1.2.1
[1.2.0]: https://github.com/shawnrancatore/synology-share-downloader/releases/tag/v1.2.0
[1.1.0]: https://github.com/shawnrancatore/synology-share-downloader/releases/tag/v1.1.0
[1.0.2]: https://github.com/shawnrancatore/synology-share-downloader/releases/tag/v1.0.2
[1.0.1]: https://github.com/shawnrancatore/synology-share-downloader/releases/tag/v1.0.1
[1.0.0]: https://github.com/shawnrancatore/synology-share-downloader/releases/tag/v1.0.0
