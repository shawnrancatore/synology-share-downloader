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
"""The Help menu and the About dialog."""

import tkinter as tk
import webbrowser
from tkinter import ttk

from . import APP_NAME, COMPANY, COMPANY_TAGLINE, COPYRIGHT, DOCS_URL, LICENSE_NAME, LICENSE_URL, REPO_URL, __version__


def build_help_menu(root, menubar):
    """Attach a Help menu (Documentation / GitHub / About) to menubar."""
    helpm = tk.Menu(menubar, tearoff=0)
    helpm.add_command(label="Documentation…",
                      command=lambda: webbrowser.open(DOCS_URL))
    helpm.add_command(label="Project on GitHub…",
                      command=lambda: webbrowser.open(REPO_URL))
    helpm.add_separator()
    helpm.add_command(label="About %s…" % APP_NAME,
                      command=lambda: show_about(root))
    menubar.add_cascade(label="Help", menu=helpm)
    return helpm


def show_about(root):
    win = tk.Toplevel(root)
    win.title("About %s" % APP_NAME)
    win.resizable(False, False)
    win.transient(root)
    win.grab_set()

    frame = ttk.Frame(win, padding=20)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 14, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Version %s" % __version__,
              foreground="#555").pack(anchor="w", pady=(0, 10))

    ttk.Label(frame, text="%s — %s" % (COMPANY, COMPANY_TAGLINE),
              font=("Segoe UI", 10, "bold")).pack(anchor="w")
    ttk.Label(frame, text=COPYRIGHT).pack(anchor="w", pady=(0, 10))

    ttk.Label(frame,
              text="Reliable, resumable, file-by-file downloads from\n"
                   "Synology folder-share links — no giant ZIP.",
              foreground="#333", justify="left").pack(anchor="w", pady=(0, 10))

    lic = ttk.Frame(frame)
    lic.pack(anchor="w")
    ttk.Label(lic, text="License: ").pack(side="left")
    _link(lic, LICENSE_NAME, LICENSE_URL)

    proj = ttk.Frame(frame)
    proj.pack(anchor="w", pady=(2, 12))
    ttk.Label(proj, text="Website: ").pack(side="left")
    _link(proj, REPO_URL, REPO_URL)

    ttk.Button(frame, text="Close", command=win.destroy).pack(anchor="e")

    win.update_idletasks()
    # center over parent
    x = root.winfo_rootx() + (root.winfo_width() - win.winfo_width()) // 2
    y = root.winfo_rooty() + (root.winfo_height() - win.winfo_height()) // 3
    win.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
    win.bind("<Escape>", lambda _e: win.destroy())
    win.focus_set()


def _link(parent, text, url):
    lbl = ttk.Label(parent, text=text, foreground="#1a6fdb", cursor="hand2")
    lbl.pack(side="left")
    f = lbl.cget("font")
    try:
        import tkinter.font as tkfont
        font = tkfont.Font(font=f)
        font.configure(underline=True)
        lbl.configure(font=font)
    except Exception:
        pass
    lbl.bind("<Button-1>", lambda _e: webbrowser.open(url))
    return lbl
