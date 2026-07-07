# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.0]: https://github.com/shawnrancatore/synology-share-downloader/releases/tag/v1.0.0
