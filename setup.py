"""
py2app build script for Statement Splitter.

Build STANDALONE so the .app carries its own Python + Tk and opens on a Mac
with nothing installed:

    source venv/bin/activate
    rm -rf build "dist/Statement Splitter.app"
    python setup.py py2app --no-strip

Then ./build_dmg.sh wraps it in a drag-to-install disk image.
"""
import sys
from pathlib import Path

from setuptools import setup

from version import APP_NAME, APP_VERSION

APP = ["app.py"]
DATA_FILES = [(".", ["appicon_128.png", "CHANGELOG.md"])]

# The scanned-bill reader (tesseract + English data, and poppler's pdftoppm to
# turn a PDF page into a picture), built in so bill copies can be read on a
# Mac with no Homebrew. Staged from this Mac's Homebrew by stage_mac_ocr.py
# (the same bundle the sibling check-register-app ships, already notarized);
# lands in Contents/Resources/tesseract and poppler/, where bills._tools() looks.
if sys.platform == "darwin" and "py2app" in sys.argv:
    VENDOR = Path(__file__).resolve().parent / "vendor_mac"
    OCR, POPPLER = VENDOR / "tesseract", VENDOR / "poppler" / "bin"
    if not ((OCR / "tesseract").exists() and (POPPLER / "pdftoppm").exists()):
        import stage_mac_ocr
        stage_mac_ocr.stage()
    DATA_FILES += [
        ("tesseract", [str(OCR / "tesseract")]),
        ("tesseract/lib", sorted(str(f) for f in (OCR / "lib").iterdir())),
        ("tesseract/tessdata", [str(OCR / "tessdata" / "eng.traineddata")]),
        ("poppler/bin", [str(POPPLER / "pdftoppm"), str(POPPLER / "pdfinfo")]),
        ("poppler/bin/lib", sorted(str(f) for f in (POPPLER / "lib").iterdir())),
    ]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "appicon.icns",
    "packages": ["pypdf", "certifi", "openpyxl", "et_xmlfile"],
    # pypdf *optionally* imports Pillow, so py2app drags it in along with a
    # dozen image libraries — some end up inside the python zip where they
    # cannot be code-signed, and Apple's notary service rejects the app.
    # The splitter never touches images, so leave all of that out.
    "excludes": ["PIL", "reportlab", "py2app", "setuptools", "pip", "test", "unittest"],
    "includes": ["tkinter"],
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.satherflynn.statementsplitter",
        "CFBundleVersion": APP_VERSION,
        "CFBundleShortVersionString": APP_VERSION,
        "NSHighResolutionCapable": True,
        # Launching from Finder gives a bare environment with no locale;
        # force UTF-8 so file names with odd characters never trip us up.
        "LSEnvironment": {"PYTHONUTF8": "1"},
    },
}

setup(
    app=APP,
    name=APP_NAME,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
