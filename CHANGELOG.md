# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **Downloads stay inside the destination folder.** File and folder names come
  from the server, and a hostile share could list names such as `../x`,
  `..\x` or `D:x` to write outside the folder you chose. Every local path is
  now checked first. A name is skipped, with a `Skipped …` line in the log,
  if it:
  - has a `.`, `..` or empty part, a backslash, a `:`, a control character,
    or one of `< > " | ? *`;
  - ends with a dot or a space;
  - is a Windows device name, such as `CON`, `NUL` or `COM1.txt`;
  - is listed outside the folder being downloaded;
  - would resolve outside the destination through an existing symbolic link,
    or its `.part` file would.

  The same rules apply on every OS. A skipped folder is not listed at all.
- **The app never writes through a symbolic link.** If the file to write, or
  its `.part` file, is a symbolic link, the file is skipped and logged. The
  link's target is not written, re-stamped or replaced. A `.part` file that has
  another hard link is skipped as well, before a byte of it changes. The final
  line counts both as `link(s) skipped`. A symbolic link to a folder is
  followed only when it leads inside the destination. A local user who can
  rewrite folders inside the destination during a download is out of scope.
- **Unverified connections are visible, and the app asks first.** The
  QuickConnect lookup and the NAS's QuickConnect name still use verified HTTPS.
  The fallback to the NAS's public IP, DDNS name and LAN addresses, which skips
  certificate checks, now logs `certificate not verified for <host>`, and the
  app asks before it sends the share password over such a connection (once per
  address, per run). `SynoShareClient` takes a `confirm_unverified(host)`
  callback for the same purpose.
- urllib3's `InsecureRequestWarning` is no longer silenced for the whole
  process; it is silenced only for the unverified addresses the app tries.
- **The log keeps the share link secret.** It shows only the link's scheme,
  host and first path segment, and replaces the rest, which holds the share's
  id, with `…` (`http://gofile.me/AbCdE/…`). That holds however the link was
  pasted: percent-encoded, with backslashes, or with extra segments. Text that
  is not a plain host and path is logged as `…`. Error messages go through the
  same redaction, so they no longer quote the id from the link or from a
  request URL.
- The bug-report form warns not to paste share links or passwords, and says
  what the log does show.

### Fixed
- A file or folder picked directly in the tree now keeps its original dates.
  Before, only the items inside a picked folder did.
- The User-Agent carries the app's version instead of `1.0`.

### Changed
- Examples and tests use an obviously fake share link,
  `http://gofile.me/AbCdE/ExAmPlE123`.
- Package classifiers say "OS Independent" and "4 - Beta".
- The docs match the builds: zip and tar.gz archives (no bare `.exe`), macOS
  on Apple Silicon only, creation dates set on Windows only, completeness
  checked by size only, and direct connections only (no QuickConnect relay).
- The README follows the bricoleur.ai layout, with a "What it deliberately
  does not do" section and a link to the full guide. Its verification commands
  now name the archives: `SHA256SUMS.txt` and the attestation cover the
  archives, not the `.exe` inside. The old screenshot, which showed an earlier
  version, is replaced by a diagram.

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
