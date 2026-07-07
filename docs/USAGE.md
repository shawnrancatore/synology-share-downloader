# Using Synology Share Downloader

A friendly, step-by-step guide for downloading files from a Synology share link.

## What you need

- The **share link** — it looks like `http://gofile.me/75lxK/7vqFT49uA`.
- The **password** for that share (if it's password-protected).
- A Windows PC.

You do **not** need a Synology account or any login of your own.

## 1. Get the app

Download the latest release from the project's **Releases** page:

- `SynologyShareDownloader-vX.Y.Z-win64.zip` — unzip it anywhere (Desktop is
  fine), **or**
- `SynologyShareDownloader.exe` — the app on its own.

Then double-click **`SynologyShareDownloader.exe`**. Nothing installs; it just
opens.

> **SmartScreen warning?** Because the app isn't code-signed, Windows may show
> *"Windows protected your PC."* Click **More info → Run anyway**. (If you'd
> rather not trust a prebuilt file, you can build it yourself from source — see
> the README.)

## 2. Connect to the share

![Connect](images/step-connect.png)

1. Paste the **share link** into the *Share link* box.
2. Type the **password**.
3. Click **Connect**.

After a moment the shared folder appears in the list. If the password is wrong
or the NAS can't be reached, you'll see a clear message explaining why.

## 3. Choose what to download

- Click the **▸ arrows** to open folders and look inside.
- Click an item to select it. Hold **Ctrl** and click to select several, or
  **Shift**-click to select a range.
- You can select whole **folders** (everything inside comes along, with the
  same structure) or individual **files**.

> **Tip:** Some shares expose a very large tree at the top level. Open the tree
> and pick the specific subfolder you actually want rather than the entire root.

## 4. Choose where to save

Next to **Save to**, click **Browse…** and pick a destination folder on your
computer. The app recreates the shared folder's structure underneath it.

## 5. Download

Click **Download selected**. You'll see:

- an **overall** progress bar (all selected files),
- a **current file** progress bar,
- the file name, counts, transfer speed, and estimated time remaining.

When it finishes, your files are in the destination folder — with their
**original dates** preserved, so they sort and look the way you expect.

## Resuming and re-running

Downloads are **resumable**:

- If the network drops or you close the app mid-download, just open it again,
  connect, select the same folder and the same destination, and click
  **Download selected** again.
- Files that already finished are **skipped instantly**.
- A file that was only half-downloaded **continues** from where it stopped
  (it's stored as a `.part` file until complete).

The **Cancel** button stops after the current chunk; your progress is kept for
resuming later.

## Frequently asked questions

**Do I need the NAS owner to do anything?**
No — as long as the share link works in a web browser, it works here.

**Where did my files go?**
Into the *Save to* folder you chose, inside a subfolder matching the shared
folder's name and structure.

**It says it can't reach the server.**
The NAS must be online and remotely reachable (the same thing that makes the
web link open in a browser). Try opening the link in a browser to confirm the
share is up.

**Is my password stored anywhere?**
No. It's used only to log in to the share for the current session and is not
saved to disk.

**Can I use it on macOS or Linux?**
The code is cross-platform Python, but official release builds are Windows-only
for now. You can run it from source (`python app.py`) on other systems.

## About

Open the **Help → About** menu to see the version, license, and project link.

Synology Share Downloader is free and open source under the Apache License 2.0.
© 2026 Dynamo Foundry LLC — a Software Company.
