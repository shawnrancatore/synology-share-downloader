# Contributing

Thanks for your interest in improving **Synology Share Downloader**! The goal of
this project is to be *the* shared, community-maintained tool for this job — so
contributions that make it more reliable, friendlier, or more broadly useful are
very welcome.

## Ways to help

- **Report bugs** or request features via
  [Issues](../../issues) — please use the templates.
- **Improve docs** — the end-user guide is [docs/USAGE.md](docs/USAGE.md).
- **Send code** — bug fixes, features, tests, packaging, ports.

## Development setup

Requires Python 3.9+.

```bash
git clone https://github.com/shawnrancatore/synology-share-downloader
cd synology-share-downloader
python -m venv .venv
# Windows:  .venv\Scripts\activate     macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt
```

Run from source:

```bash
python app.py            # or:  python -m synology_share_downloader
```

## Before you open a pull request

1. **Discuss big changes first** in an issue so effort isn't wasted.
2. **Keep PRs focused** — one logical change per PR.
3. **Run the checks:**
   ```bash
   ruff check .
   pytest
   ```
4. **Match the style** — standard library + `requests` only for the runtime;
   keep the GUI dependency-free (Tkinter). Prefer clear code over cleverness.
5. **Update docs** (`README.md` / `docs/USAGE.md`) and `CHANGELOG.md` when
   behavior changes.
6. If you change how a file behaves, note it — the Apache License asks that
   modified files carry a note that they were changed.

## Project layout

```
synology_share_downloader/
  __init__.py     # version + branding metadata (single source of truth)
  client.py       # the share protocol: resolve, login, list, resumable download
  gui.py          # the Tkinter application
  about.py        # Help menu + About dialog
  util.py         # small formatting helpers (no GUI/network)
app.py            # launcher / PyInstaller entry point
build.py          # builds the portable .exe (+ .zip)
docs/USAGE.md     # end-user documentation
tests/            # unit tests (no network needed)
```

## Releasing (maintainers)

1. Bump `__version__` in `synology_share_downloader/__init__.py` and update
   `CHANGELOG.md`.
2. Commit, then tag: `git tag v1.2.3 && git push origin v1.2.3`.
3. GitHub Actions builds the Windows `.exe`, packages the portable `.zip`, and
   attaches both to a new GitHub Release automatically.

## Code of Conduct

By participating you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

## License of contributions

Unless you state otherwise, contributions you submit are licensed under the
project's [Apache License 2.0](LICENSE).
