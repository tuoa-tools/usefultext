UsefulText turns photos of document pages (and PDFs) into text and markdown, entirely on
your machine. Nothing is uploaded; the OCR engine and its models are inside the app.

**Install**

- **macOS**: download the zip for your Mac (`macos-arm64` for Apple Silicon, `macos-x64` for
  Intel), unzip, and drag UsefulText to Applications. The first time, macOS says the app
  "cannot be opened because the developer cannot be verified" — it is not signed with an
  Apple developer certificate. **Right-click (or Control-click) the app and choose Open**,
  then Open again in the dialog; after that it opens normally. (If that is refused: open
  System Settings → Privacy & Security and choose "Open Anyway", or in Terminal run
  `xattr -d com.apple.quarantine /Applications/UsefulText.app`.)
- **Windows**: run `UsefulText-windows-x64-setup.exe`. It installs for your user only (no
  administrator needed). SmartScreen may ask "More info → Run anyway" the first time. The
  app opens in your browser; close the tab and the app exits by itself a couple of minutes
  later, once nothing is being read.
- **Linux**: unpack the tarball anywhere and run `UsefulText/UsefulText`. With WebKitGTK and
  PyGObject installed it opens in its own window; otherwise in your browser.

On first start the app asks where your library folder should live; every document you
read becomes a folder there with its photos, its text and your corrections. Settings and
the log (`app.log`) are in your user's app-data folder.

**What's in this release**

v0.3.1: on Windows the app opens in your browser (the app's own window misbehaved on a real Windows 11 machine and is opt-in there for now); the first-run screen shows an error instead of "Loading…" when something is wrong; the window hands the page its launch token directly.
