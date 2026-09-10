# PyInstaller spec: onedir, windowed build of the desktop app (server + built UI + the OCR
# engine with its three models). Build from the repo root, after `npm run build` in frontend/
# and `python scripts/prepare_bundle.py`:
#
#     pyinstaller --noconfirm --clean packaging/UsefulText.spec
#
# macOS: dist/UsefulText.app; Linux: dist/UsefulText/. Windows uses scripts/build_windows.py.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from usefultext import __version__  # noqa: E402

ICON = {
    "darwin": ROOT / "packaging" / "icon.icns",
    "win32": ROOT / "packaging" / "icon.ico",
}.get(sys.platform)

datas = [
    (str(ROOT / "app" / "static"), "app/static"),  # `npm run build` output
    (str(ROOT / "packaging" / "models"), "models"),  # scripts/prepare_bundle.py output
]
# rapidocr's config and model index, but not its 260 MB of models (we ship three).
datas += [
    (src, dest)
    for src, dest in collect_data_files("rapidocr")
    if not Path(src).suffix == ".onnx"
]
datas += collect_data_files("spellchecker")  # the word-frequency lists
datas += collect_data_files("webview")  # pywebview's injected JS

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "pillow_heif",
    "docx",
]
hiddenimports += collect_submodules("rapidocr")
if sys.platform == "darwin":
    hiddenimports += ["webview.platforms.cocoa", "objc", "Foundation", "AppKit", "WebKit", "Security"]

a = Analysis(
    [str(ROOT / "app" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "tkinter",
        "pytest",
        "IPython",
        "torch",
        "torchvision",
        "paddle",
        "openvino",
        "matplotlib",
        "scipy",
        "pandas",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="UsefulText",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # windowed: no terminal; logs go to app.log in the app-data folder
    icon=str(ICON) if ICON and ICON.exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="UsefulText")
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="UsefulText.app",
        icon=str(ICON) if ICON and ICON.exists() else None,
        bundle_identifier="au.com.tuoa.usefultext",
        info_plist={
            "CFBundleName": "UsefulText",
            "CFBundleDisplayName": "UsefulText",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "MIT licence · tuoa-tools/usefultext",
        },
    )
