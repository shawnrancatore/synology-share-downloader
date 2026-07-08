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
"""Tkinter GUI: connect to a share, browse it, pick what to download."""

import concurrent.futures as cf
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME
from .about import build_help_menu
from .client import ShareError, SynoShareClient, apply_file_times
from .util import format_eta as _fmt_time
from .util import human_size as human


class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.geometry("860x640")
        root.minsize(720, 520)

        self.client = None
        self.q = queue.Queue()
        self.nodes = {}          # tree item id -> {path, isdir, size, loaded}
        self.worker = None
        self.stop_flag = threading.Event()
        self.downloading = False
        self.confirm_event = threading.Event()
        self.confirm_result = False

        self._build_menu()
        self._build_ui()
        self.root.after(80, self._pump)

    # ------------------------------------------------------------------ UI
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        filem = tk.Menu(menubar, tearoff=0)
        filem.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=filem)
        build_help_menu(self.root, menubar)
        self.root.config(menu=menubar)

    def _build_ui(self):
        pad = dict(padx=6, pady=4)

        # --- connection row ---
        top = ttk.LabelFrame(self.root, text="1.  Connect to the share")
        top.pack(fill="x", **pad)

        ttk.Label(top, text="Share link:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self.url_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.url_var, width=52).grid(row=0, column=1, sticky="we", padx=4, pady=4)

        ttk.Label(top, text="Password:").grid(row=0, column=2, sticky="e", padx=4, pady=4)
        self.pw_var = tk.StringVar()
        self.pw_entry = ttk.Entry(top, textvariable=self.pw_var, width=20, show="•")
        self.pw_entry.grid(row=0, column=3, sticky="we", padx=4, pady=4)

        self.connect_btn = ttk.Button(top, text="Connect", command=self.on_connect)
        self.connect_btn.grid(row=0, column=4, padx=6, pady=4)
        top.columnconfigure(1, weight=1)

        # --- browser ---
        mid = ttk.LabelFrame(self.root, text="2.  Choose folders / files to download")
        mid.pack(fill="both", expand=True, **pad)

        self.tree = ttk.Treeview(mid, selectmode="extended", columns=("size",))
        self.tree.heading("#0", text="Name")
        self.tree.heading("size", text="Size")
        self.tree.column("size", width=110, anchor="e", stretch=False)
        self.tree.column("#0", width=520)
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewOpen>>", self.on_expand)

        # --- destination + actions ---
        bottom = ttk.LabelFrame(self.root, text="3.  Destination & download")
        bottom.pack(fill="x", **pad)

        row0 = ttk.Frame(bottom)
        row0.pack(fill="x", padx=4, pady=4)
        ttk.Label(row0, text="Save to:").pack(side="left")
        self.dest_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        ttk.Entry(row0, textvariable=self.dest_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row0, text="Browse…", command=self.on_browse_dest).pack(side="left")

        row1 = ttk.Frame(bottom)
        row1.pack(fill="x", padx=4, pady=(0, 4))
        self.download_btn = ttk.Button(row1, text="Download selected",
                                       command=self.on_download, state="disabled")
        self.download_btn.pack(side="left")
        self.download_all_btn = ttk.Button(row1, text="Download entire share…",
                                           command=self.on_download_all, state="disabled")
        self.download_all_btn.pack(side="left", padx=6)
        self.cancel_btn = ttk.Button(row1, text="Cancel", command=self.on_cancel, state="disabled")
        self.cancel_btn.pack(side="left")
        ttk.Label(row1, text="Parallel:").pack(side="left", padx=(14, 2))
        self.parallel_var = tk.IntVar(value=4)
        ttk.Spinbox(row1, from_=1, to=8, width=3, textvariable=self.parallel_var).pack(side="left")

        # progress
        self.overall = ttk.Progressbar(bottom, mode="determinate")
        self.overall.pack(fill="x", padx=6, pady=(6, 0))
        self.cur = ttk.Progressbar(bottom, mode="determinate")
        self.cur.pack(fill="x", padx=6, pady=2)
        self.prog_lbl = ttk.Label(bottom, text="")
        self.prog_lbl.pack(fill="x", padx=6, anchor="w")

        # --- log / status ---
        self.status = tk.StringVar(value="Enter a share link and password, then click Connect.")
        ttk.Label(self.root, textvariable=self.status, anchor="w").pack(fill="x", padx=8)
        logf = ttk.Frame(self.root)
        logf.pack(fill="both", padx=6, pady=(0, 6))
        self.log = tk.Text(logf, height=7, wrap="word", state="disabled",
                           bg="#111", fg="#ddd", font=("Consolas", 9))
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")

    # --------------------------------------------------------------- helpers
    def log_msg(self, msg):
        self.q.put(("log", msg))

    def set_status(self, msg):
        self.q.put(("status", msg))

    def _append_log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ----------------------------------------------------------- connect
    def on_connect(self):
        if self.downloading:
            return
        url = self.url_var.get().strip()
        pw = self.pw_var.get()
        if not url:
            messagebox.showwarning(APP_NAME, "Please paste the share link.")
            return
        self.connect_btn.configure(state="disabled")
        self.download_btn.configure(state="disabled")
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.nodes.clear()
        self.set_status("Connecting…")
        self._append_log("Connecting to %s" % url)

        def work():
            try:
                client = SynoShareClient(url, pw, log=self.log_msg)
                client.resolve()
                client.login()
                entries = client.list_folder(client.root_path)
                self.q.put(("connected", (client, entries)))
            except ShareError as e:
                self.q.put(("connect_fail", str(e)))
            except Exception as e:
                self.q.put(("connect_fail", "Unexpected error: %s" % e))

        threading.Thread(target=work, daemon=True).start()

    def _on_connected(self, payload):
        self.client, entries = payload
        self.connect_btn.configure(state="normal")
        root_item = self.tree.insert(
            "", "end", text="  " + self.client.root_path.strip("/") + "  (share root)",
            open=True, values=("",))
        self.nodes[root_item] = {"path": self.client.root_path, "isdir": True,
                                 "size": 0, "loaded": True}
        self._fill_children(root_item, entries)
        self.download_btn.configure(state="normal")
        self.download_all_btn.configure(state="normal")
        self.set_status("Connected. Select folders/files and choose a destination.")

    def _fill_children(self, parent_item, entries):
        # folders first, then files, both already name-sorted by the server
        for e in sorted(entries, key=lambda x: (not x["isdir"], (x["name"] or "").lower())):
            label = ("  \U0001F4C1 " if e["isdir"] else "  \U0001F4C4 ") + (e["name"] or "")
            item = self.tree.insert(parent_item, "end", text=label,
                                    values=("" if e["isdir"] else human(e["size"]),))
            self.nodes[item] = {"path": e["path"], "isdir": e["isdir"],
                                "size": e["size"], "loaded": not e["isdir"]}
            if e["isdir"]:
                self.tree.insert(item, "end", text="  loading…")  # placeholder arrow

    def on_expand(self, _evt):
        item = self.tree.focus()
        meta = self.nodes.get(item)
        if not meta or not meta["isdir"] or meta["loaded"]:
            return
        meta["loaded"] = True
        for child in self.tree.get_children(item):
            self.tree.delete(child)  # remove placeholder

        def work():
            try:
                entries = self.client.list_folder(meta["path"])
                self.q.put(("children", (item, entries)))
            except ShareError as e:
                self.q.put(("log", "List failed: %s" % e))

        threading.Thread(target=work, daemon=True).start()

    # ----------------------------------------------------------- download
    def on_browse_dest(self):
        d = filedialog.askdirectory(initialdir=self.dest_var.get() or os.path.expanduser("~"))
        if d:
            self.dest_var.set(d)

    def on_download(self):
        if self.downloading or not self.client:
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select one or more folders/files in the list first.")
            return
        dest = self.dest_var.get().strip()
        if not dest:
            messagebox.showwarning(APP_NAME, "Choose a destination folder.")
            return
        # Build the list of top-level items to fetch (dedupe nested selections).
        picks = []
        sel_paths = {self.nodes[i]["path"] for i in sel if i in self.nodes}
        for i in sel:
            m = self.nodes.get(i)
            if not m:
                continue
            if any(m["path"] != p and m["path"].startswith(p + "/") for p in sel_paths):
                continue  # an ancestor is also selected
            picks.append(m)
        if not picks:
            return
        self._start_download(picks, dest, confirm=False)

    def on_download_all(self):
        if self.downloading or not self.client:
            return
        dest = self.dest_var.get().strip()
        if not dest:
            messagebox.showwarning(APP_NAME, "Choose a destination folder.")
            return
        root_meta = {"path": self.client.root_path, "isdir": True, "size": 0,
                     "mtime": None, "crtime": None}
        self._start_download([root_meta], dest, confirm=True)

    def _start_download(self, picks, dest, confirm):
        try:
            workers = max(1, min(8, int(self.parallel_var.get() or 4)))
        except (tk.TclError, ValueError):
            workers = 4
        self.stop_flag.clear()
        self.downloading = True
        for b in (self.download_btn, self.download_all_btn, self.connect_btn):
            b.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.overall["value"] = 0
        self.cur["value"] = 0
        self.worker = threading.Thread(target=self._download_worker,
                                       args=(picks, dest, confirm, workers), daemon=True)
        self.worker.start()

    def _download_worker(self, picks, dest, confirm, workers):
        try:
            # 1) enumerate every file to download (and every folder to re-stamp)
            self.set_status("Scanning selected items…")
            jobs = []        # (remote_path, local_path, size, mtime, crtime)
            dir_stamps = []   # (local_path, mtime, crtime) -- applied last
            total_bytes = 0
            scanned = 0

            def local_of(remote_path, base_parent):
                rel = remote_path[len(base_parent):].lstrip("/")
                return os.path.join(dest, *rel.split("/"))

            for m in picks:
                base_parent = m["path"].rsplit("/", 1)[0]
                if m["isdir"]:
                    # the picked folder itself, then everything under it
                    dir_stamps.append((local_of(m["path"], base_parent),
                                       m.get("mtime"), m.get("crtime")))
                    for e in self.client.walk(m["path"], stop=self.stop_flag.is_set):
                        lp = local_of(e["path"], base_parent)
                        if e["isdir"]:
                            dir_stamps.append((lp, e.get("mtime"), e.get("crtime")))
                        else:
                            jobs.append((e["path"], lp, e["size"],
                                         e.get("mtime"), e.get("crtime")))
                            total_bytes += e["size"]
                        scanned += 1
                        if scanned % 200 == 0:
                            self.set_status("Scanning… %d files, %s so far" %
                                            (len(jobs), human(total_bytes)))
                else:
                    jobs.append((m["path"], local_of(m["path"], base_parent),
                                 m["size"], m.get("mtime"), m.get("crtime")))
                    total_bytes += m["size"]
                if self.stop_flag.is_set():
                    break

            if self.stop_flag.is_set():
                self.q.put(("dl_done", "Cancelled before starting."))
                return
            self.log_msg("Found %d file(s) in %d folder(s), %s total." %
                         (len(jobs), len(dir_stamps), human(total_bytes)))

            # 2) size confirmation (for "Download entire share")
            if confirm:
                self.confirm_result = False
                self.confirm_event.clear()
                self.q.put(("confirm", (total_bytes, len(jobs))))
                self.confirm_event.wait()
                if not self.confirm_result:
                    self.q.put(("dl_done", "Cancelled — nothing downloaded."))
                    return

            # 3) download in parallel, each file resumable + skip-if-complete
            st = {"bytes": 0, "files": 0, "skipped": 0, "failed": []}
            active = {}
            lock = threading.Lock()
            start = time.time()
            last_emit = [0.0]
            njobs = len(jobs)

            def emit(force=False):
                now = time.time()
                with lock:
                    cur = st["bytes"] + sum(active.values())
                    df, na = st["files"], len(active)
                if not force and now - last_emit[0] < 0.12 and cur < total_bytes:
                    return
                last_emit[0] = now
                elapsed = max(now - start, 0.001)
                speed = cur / elapsed
                remain = (total_bytes - cur) / speed if speed > 0 else 0
                self.q.put(("progress", {
                    "overall": (cur / total_bytes * 100) if total_bytes else 100,
                    "cur": (df / njobs * 100) if njobs else 100,
                    "text": "%d/%d files  •  %d active  •  %s / %s  •  %s/s  •  ~%s left" % (
                        df, njobs, na, human(cur), human(total_bytes),
                        human(speed), _fmt_time(remain)),
                }))

            def do_job(job):
                rpath, lpath, size, mtime, crtime = job
                if self.stop_flag.is_set():
                    return
                name = os.path.basename(lpath)
                try:
                    if os.path.exists(lpath) and size and os.path.getsize(lpath) == size:
                        apply_file_times(lpath, mtime, crtime)
                        with lock:
                            st["bytes"] += size
                            st["files"] += 1
                            st["skipped"] += 1
                        emit()
                        return
                    with lock:
                        active[rpath] = 0

                    def prog(d, t, _fid=rpath):
                        with lock:
                            active[_fid] = d
                        emit()

                    ok = self.client.download_file(
                        rpath, lpath, size if size else None,
                        progress=prog, stop=self.stop_flag.is_set,
                        mtime=mtime, crtime=crtime)
                    with lock:
                        got = active.pop(rpath, 0)
                        if ok:
                            st["bytes"] += size or got
                            st["files"] += 1
                except ShareError as e:
                    with lock:
                        active.pop(rpath, None)
                        st["failed"].append(name)
                    self.log_msg("FAILED %s -- %s" % (name, e))
                except Exception as e:
                    with lock:
                        active.pop(rpath, None)
                        st["failed"].append(name)
                    self.log_msg("ERROR %s -- %s" % (name, e))
                emit()

            with cf.ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(do_job, jobs))
            emit(force=True)

            if self.stop_flag.is_set():
                self.q.put(("dl_done", "Cancelled. %d file(s) finished." % st["files"]))
                return

            # 4) restore folder timestamps LAST -- writing files into a folder
            # bumps its modified time, so this must happen after every file and
            # subfolder exists. os.utime on a folder does not touch its parent,
            # so order doesn't matter; empty folders are created too.
            self.set_status("Restoring folder dates…")
            for lp, mt, ct in dir_stamps:
                try:
                    os.makedirs(lp, exist_ok=True)
                except OSError:
                    pass
            for lp, mt, ct in dir_stamps:
                apply_file_times(lp, mt, ct)

            msg = "Done. %d file(s) downloaded" % st["files"]
            if st["skipped"]:
                msg += " (%d already complete)" % st["skipped"]
            if st["failed"]:
                msg += "; %d failed" % len(st["failed"])
            if dir_stamps:
                msg += "; %d folder date(s) preserved" % len(dir_stamps)
            self.q.put(("dl_done", msg + "."))
        except Exception as e:
            self.q.put(("dl_done", "Stopped: %s" % e))

    def _ask_confirm(self, total_bytes, nfiles):
        warn = ""
        if total_bytes > 5 * 1024 ** 3:
            warn = ("\n\n⚠  This is a large download. It may include big system "
                    "files (e.g. pagefile.sys, hiberfil.sys). Make sure you have "
                    "enough free disk space, and consider selecting only the "
                    "folders you need instead.")
        ok = messagebox.askyesno(
            APP_NAME,
            "Download the entire share to:\n%s\n\n%d files, %s total.%s\n\nContinue?"
            % (self.dest_var.get(), nfiles, human(total_bytes), warn))
        self.confirm_result = bool(ok)
        self.confirm_event.set()

    def on_cancel(self):
        if self.downloading:
            self.stop_flag.set()
            self.set_status("Cancelling…")

    # ------------------------------------------------------------- pump
    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "status":
                    self.status.set(payload)
                elif kind == "connected":
                    self._on_connected(payload)
                elif kind == "connect_fail":
                    self.connect_btn.configure(state="normal")
                    self.set_status("Not connected.")
                    self._append_log("ERROR: " + payload)
                    messagebox.showerror(APP_NAME, payload)
                elif kind == "children":
                    item, entries = payload
                    self._fill_children(item, entries)
                elif kind == "progress":
                    self.overall["value"] = payload["overall"]
                    self.cur["value"] = payload["cur"]
                    self.prog_lbl.configure(text=payload["text"])
                elif kind == "confirm":
                    self._ask_confirm(*payload)
                elif kind == "dl_done":
                    self.downloading = False
                    for b in (self.download_btn, self.download_all_btn, self.connect_btn):
                        b.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
                    self.cur["value"] = 0
                    self.set_status(payload)
                    self._append_log(payload)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)


def _set_window_icon(root):
    try:
        from .icon_data import ICON_PNG_B64
        root._icon_img = tk.PhotoImage(data=ICON_PNG_B64)  # keep a reference
        root.iconphoto(True, root._icon_img)
    except Exception:
        pass


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")  # nicer on Windows
    except tk.TclError:
        pass
    _set_window_icon(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
