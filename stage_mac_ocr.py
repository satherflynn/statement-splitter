"""Stage the scanned-bill reader (tesseract) for the Mac app.

Copied from the sibling check-register-app, where this exact bundle has been
notarized by Apple. The owner's Mac has no Homebrew, so the .app must carry its own copy of
tesseract, every library it loads, and the English language data. This copies
them from this Mac's Homebrew into vendor_mac/:

    vendor_mac/tesseract/tesseract            the program
    vendor_mac/tesseract/lib/*.dylib          its libraries (leptonica, libarchive, ...)
    vendor_mac/tesseract/tessdata/eng.traineddata
    vendor_mac/poppler/bin/pdftoppm, pdfinfo  turn PDF pages into pictures
    vendor_mac/poppler/bin/lib/*.dylib        their libraries

and rewires each file so it looks for its libraries next to itself instead of
in /opt/homebrew (install_name_tool), then re-signs them ad hoc — Apple
silicon refuses to run a binary whose signature no longer matches.
sign_and_notarize.sh later re-signs everything with the Developer ID.

Apple-silicon only: Homebrew here is arm64. On an Intel Mac bills.py finds
no working reader and files every bill copy under "Unsorted pages" with a
note, rather than guessing.

Run by setup.py automatically when vendor_mac/ is missing; run by hand
(`python stage_mac_ocr.py`) after `brew upgrade tesseract` to refresh it.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "vendor_mac" / "tesseract"
SYSTEM_PREFIXES = ("/usr/lib/", "/System/")
HOMEBREW_LIBS = [Path("/opt/homebrew/lib"), Path("/usr/local/lib")]


def _run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def _deps(macho: Path) -> list[str]:
    """Install names this file links against (first line is the file itself)."""
    lines = _run("otool", "-L", str(macho)).splitlines()[1:]
    return [ln.strip().split(" (")[0] for ln in lines]


def _resolve(dep: str) -> Path | None:
    """Where a non-system dependency actually lives on this Mac."""
    if dep.startswith(SYSTEM_PREFIXES):
        return None
    if dep.startswith("/"):
        return Path(os.path.realpath(dep))
    name = dep.rsplit("/", 1)[-1]            # @rpath/... or @loader_path/...
    roots = HOMEBREW_LIBS + sorted(Path("/opt/homebrew/opt").glob("*/lib"))
    for root in roots:                       # keg-only libraries live in opt/*/lib
        cand = root / name
        if cand.exists():
            return Path(os.path.realpath(cand))
    raise SystemExit(f"Can't find library {dep!r} needed by tesseract")


def _stage_programs(programs: list[Path], out_dir: Path) -> list[Path]:
    """Copy `programs` into out_dir and every non-system library they load
    into out_dir/lib, rewired to find each other there. Returns all files."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "lib").mkdir(parents=True)

    # Walk the dependency tree once, remembering each library by file name.
    libs: dict[str, Path] = {}
    todo = list(programs)
    seen: set[Path] = set()
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        for dep in _deps(f):
            real = _resolve(dep)
            if real is not None and real != f:
                libs.setdefault(dep.rsplit("/", 1)[-1], real)
                todo.append(real)

    targets = []
    for prog in programs:
        dst = out_dir / prog.name
        shutil.copy2(prog, dst)
        targets.append((dst, "@loader_path/lib/"))
    for name, src in libs.items():
        shutil.copy2(src, out_dir / "lib" / name)
        targets.append((out_dir / "lib" / name, "@loader_path/"))

    # Rewire: each program finds its libraries in lib/, each library finds
    # its siblings beside itself.
    for path, prefix in targets:
        os.chmod(path, 0o755)
        deps = _deps(path)                   # read before renaming anything
        if path.suffix == ".dylib":
            _run("install_name_tool", "-id", f"@loader_path/{path.name}", str(path))
        for dep in deps:
            name = dep.rsplit("/", 1)[-1]
            if dep.startswith(SYSTEM_PREFIXES) or name == path.name:
                continue                     # system library, or its own id
            _run("install_name_tool", "-change", dep, prefix + name, str(path))
        _run("codesign", "--force", "--sign", "-", str(path))

    # Nothing may still point into Homebrew.
    for path, _ in targets:
        left = [d for d in _deps(path) if d.startswith(("/opt/homebrew", "/usr/local"))]
        if left:
            raise SystemExit(f"{path.name} still links to Homebrew: {left}")
    return [t for t, _ in targets]


def _program(name: str) -> Path:
    found = shutil.which(name) or f"/opt/homebrew/bin/{name}"
    if not Path(found).exists():
        raise SystemExit(f"{name} isn't installed on this Mac: brew install tesseract poppler")
    return Path(os.path.realpath(found))


def stage() -> Path:
    """Stage tesseract (+ English data) and poppler's pdftoppm/pdfinfo."""
    root = OUT.parent
    _stage_programs([_program("tesseract")], OUT)
    (OUT / "tessdata").mkdir()
    prefix = _run("brew", "--prefix", "tesseract").strip()
    shutil.copy2(Path(prefix) / "share" / "tessdata" / "eng.traineddata",
                 OUT / "tessdata" / "eng.traineddata")
    # pdf2image calls pdfinfo (page count) and pdftoppm (the pictures).
    _stage_programs([_program("pdftoppm"), _program("pdfinfo")],
                    root / "poppler" / "bin")
    return root


if __name__ == "__main__":
    root = stage()
    for part in ("tesseract", "poppler"):
        d = root / part
        size = sum(p.stat().st_size for p in d.rglob("*") if p.is_file()) / 1e6
        print(f"Staged {part}: {size:.1f} MB in {d.relative_to(HERE)}")
    sys.exit(0)
