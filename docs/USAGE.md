# Using Synology Share Downloader

A friendly, step-by-step guide for downloading files from a Synology share link.

## What you need

- The **share link** — it looks like `http://gofile.me/AbCdE/ExAmPlE123`.
- The **password** for that share (if it's password-protected).
- A Windows, macOS, or Linux computer.

You do **not** need a Synology account or any login of your own.

## 1. Get the app

Download the build for your operating system from the project's **Releases**
page, then open it:

- **Windows** — `…-win64.zip` (unzip, then double-click
  `SynologyShareDownloader.exe`).
- **macOS** (Apple Silicon) — `…-macos-arm64.zip` (unzip, then open
  `SynologyShareDownloader.app`; drag it to Applications if you like). There is
  no build for Intel Macs; run it from source instead (see the README).
- **Linux** (x86-64) — `…-linux-x86_64.tar.gz` (`tar xzf` it, then run
  `./SynologyShareDownloader`).

There is no installer: the app runs from where you put it.

> **First-run security prompt?** The app isn't code-signed, so your OS may warn
> you the first time:
> - **Windows:** *"Windows protected your PC"* → **More info → Run anyway**.
> - **macOS:** right-click the app → **Open** → **Open** (only needed once), or
>   allow it under *System Settings → Privacy & Security*.
> - **Linux:** if it won't run, mark it executable:
>   `chmod +x SynologyShareDownloader`.
>
> If you'd rather not trust a prebuilt file, you can build it yourself — see the
> README.

## 2. Connect to the share

1. Paste the **share link** into the *Share link* box.
2. Type the **password**.
3. Click **Connect**.

After a moment the shared folder appears in the list. If the password is wrong
or the NAS can't be reached, you'll see a clear message explaining why.

### If the app asks about a certificate

The app first looks up the share through Synology's QuickConnect service and
tries the NAS's QuickConnect name. Both use HTTPS with a verified certificate.

If that name can't be reached from your network, the app tries the NAS's other
addresses: its public IP address, its DDNS name, and its addresses on the local
network. Those typically carry the NAS's own self-signed certificate, which the
app cannot check, so it connects to them without verifying the certificate.
When it does, the log shows:

```text
Warning: certificate not verified for <address>. The app cannot confirm this is your NAS.
```

Before it sends the share password over such a connection, the app asks
**Send the share password over this connection?**

- **Yes** logs in and carries on. The app doesn't ask again for that address
  until you restart it.
- **No** stops. The password is not sent.

An unverified connection doesn't prove who is at the other end. Someone between
you and the NAS could read the password and the files. Choose **Yes** when you
expect the NAS at that address, such as when you're on the NAS's own network.

## 3. Choose what to download

- Click the **▸ arrows** to open folders and look inside.
- Click an item to select it. Hold **Ctrl** and click to select several, or
  **Shift**-click to select a range.
- You can select whole **folders** (everything inside comes along, with the
  same structure) or individual **files**.

> **Tip:** Some shares expose a very large tree at the top level. Open the tree
> and pick the specific subfolder you actually want rather than the entire root.

### Or grab everything

Prefer the whole thing? Click **Download entire share…**. The app first scans
the share and then shows you **how many files and how much data** it will
download, so you can confirm before it starts (and it warns you if the total is
very large — some shares contain big system files). Choose your destination
first, as below.

### Downloading faster (parallel)

The **Parallel** box (next to the buttons) controls how many files download at
the same time — 1 to 8, default 4. Higher can be faster on good connections;
lower is gentler. You can leave it at 4.

## 4. Choose where to save

Next to **Save to**, click **Browse…** and pick a destination folder on your
computer. The app recreates the shared folder's structure underneath it.

## 5. Download

Click **Download selected**. You'll see:

- an **overall** progress bar (all selected files),
- a **current file** progress bar,
- the file name, counts, transfer speed, and estimated time remaining.

When it finishes, your files are in the destination folder, and empty folders
are recreated. Files and folders keep their **original modified dates**, so
everything sorts the way you expect. On Windows they keep their original
**creation dates** too; the app sets creation dates on Windows only.

## Resuming and re-running

Downloads are **resumable**:

- If the network drops or you close the app mid-download, open it again,
  connect, select the same folder and the same destination, and click
  **Download selected** again.
- Files that already finished are **skipped**. A file counts as finished when
  its size on disk matches the size the share lists. The app compares sizes
  only, not contents.
- A file that was only half-downloaded **continues** from where it stopped
  (it's stored as a `.part` file until complete).

The **Cancel** button stops after the current chunk; your progress is kept for
resuming later.

## Frequently asked questions

**Do I need the NAS owner to do anything?**
No, as long as the app can reach the NAS from your network (see "It says it
can't reach the server" below).

**Where did my files go?**
Into the *Save to* folder you chose. A folder you picked arrives as a folder of
the same name, with everything inside it in the same structure. A file you
picked on its own lands directly in *Save to*. **Download entire share…** puts
everything in a folder named after the share's top folder.

**The log says `Skipped …`.**
The share listed a name that Windows, macOS or Linux can't use as a plain file
name inside your *Save to* folder. Such a name could put a file outside the
folder, open a device, write to a hidden file stream, or be refused outright.
That covers a name with a `..` part, a backslash, a `:`, a control character or
one of `< > " | ? *`, and a name Windows reserves for a device, such as `CON`,
`NUL`, `COM1` or `aux.c`. The app skips such names on
every system, even one that would allow them. It doesn't download the file,
and if it's a folder, doesn't look inside it. The rest of the download carries
on. A link inside *Save to* that points to a folder somewhere else is treated
the same way.

The app also never writes through a link. If the file it would write, or its
`.part` file, is already a link, it skips that file and logs
`Skipped '<path>': it is a link, …`.

**It says it can't reach the server.**
The app connects to the NAS directly, at the addresses QuickConnect reports for
it: its QuickConnect name, public IP address, DDNS name and local addresses. It
doesn't use QuickConnect's relay service. So the NAS must be online and accept
connections on one of those addresses from your network. Away from the NAS's
own network, that needs a port on the NAS open to the internet.

**Is my password stored anywhere?**
No. It's used only to log in to the share for the current session and is not
saved to disk.

**Can I share the log when I report a problem?**
Yes, with care. The log shows only the start of the share link: the site and
the first part of the path. The rest, which holds the share's id, is replaced
by `…`, as in `Connecting to http://gofile.me/AbCdE/…`. Error messages are
cleaned the same way. The log never shows the password. It can show the NAS's
address and the names of your files,
so replace those if you'd rather not share them. Never paste the full link or
the password into an issue: issues are public.

**Why does my computer warn me the app is unrecognized?**
Because the app isn't code-signed (that needs a paid certificate). The warning
is expected — see the first-run steps above to proceed. If you'd like to be
extra careful, releases from v1.2.1 on ship a `SHA256SUMS.txt` you can check
the downloaded archive against. The release workflow also tries to record a
build-provenance attestation for each archive, but a failed attempt doesn't
stop a release, so check that one exists (see the README's
[Verify your download](../README.md#verify-your-download) section).

**Can I use it on macOS or Linux?**
Yes — the Releases page has builds for Windows, macOS on Apple Silicon, and
Linux on x86-64. You can also run it from source (`python app.py`) on any of
the three, including an Intel Mac.

## About

Open the **Help → About** menu to see the version, license, and project link.

Synology Share Downloader is free and open source under the Apache License 2.0.
© 2026 Dynamo Foundry LLC — a Software Company.
