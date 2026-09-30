"""
File each bill copy with the property it was charged to.

AppFolio's monthly download holds the owner packet plus one PDF per bill,
named "bill_<vendor invoice number>.pdf". They're usually scans, often
handwritten (a plumber's job ticket), so the property can't reliably be read
off the page. The statement can be used instead: every bill paid that month
appears as a payment on exactly one property's ledger. So:

  1. Read the bill's text: its text layer if it has one, otherwise text
     recognition (tesseract) on a picture of the first page or two. Only the
     PRINTED parts need to come through — the company letterhead.
  2. Find payments this month whose payee appears in that text (letters only,
     so "Ace Plumbing" matches "aceplumbing.com").
  3. One property paid that company  -> that's the property.
     Several properties paid it (a garbage or tax run) -> keep the candidates
     whose amount, account number, or street address also appears on the bill;
     file it only if exactly one is left.
  4. Otherwise the copy goes to "Unsorted pages" with a note saying why.

The bill is copied, never moved or changed, to
    <destination>/<property folder>/<YYYY-MM> bill - <Payee> (<number>).pdf
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from splitter import UNSORTED_NAME, _safe_filename
from version import resource_base

BILL_NAME_RE = re.compile(r"^bill_(\d+)", re.I)
ACCOUNT_RE = re.compile(r"(?<![\d/])(\d[\d-]{3,}\d)(?![\d/])")
OCR_PAGES = 2          # the letterhead and total are on the first page or two
OCR_DPI = 200


# ------------------------------------------------------------------ inputs

@dataclass
class Inputs:
    statement: Path | None
    bills: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    _tmp: tempfile.TemporaryDirectory | None = None

    def cleanup(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()


def _is_statement(pdf: Path) -> bool:
    try:
        r = PdfReader(str(pdf))
        for page in r.pages[:3]:
            if "Owner Statement" in [l.strip() for l in (page.extract_text() or "").splitlines()]:
                return True
    except Exception:
        pass
    return False


def sort_inputs(paths: list[Path]) -> Inputs:
    """Work out which chosen file is the statement and which are bill copies.
    A .zip (AppFolio's download, or a folder someone zipped) is unpacked first."""
    pdfs: list[Path] = []
    tmp = None
    for p in paths:
        if p.suffix.lower() == ".zip":
            tmp = tmp or tempfile.TemporaryDirectory(prefix="statement-splitter-")
            with zipfile.ZipFile(p) as z:
                z.extractall(tmp.name)
            pdfs += [q for q in Path(tmp.name).rglob("*.pdf")
                     if "__MACOSX" not in q.parts and not q.name.startswith("._")]
        elif p.suffix.lower() == ".pdf":
            pdfs.append(p)
    out = Inputs(statement=None, _tmp=tmp)
    statements = [p for p in pdfs if not BILL_NAME_RE.match(p.name) and _is_statement(p)]
    if statements:
        out.statement = statements[0]
        if len(statements) > 1:
            out.notes.append(f"More than one owner statement was chosen; used {statements[0].name}.")
    out.bills = sorted(p for p in pdfs if p not in statements)
    return out


# ------------------------------------------------------------------ reading a bill

def _tools() -> tuple[str | None, str | None, str | None]:
    """(tesseract, tessdata folder or None, pdftoppm). The copies built into
    the app come first; a developer Mac falls back to Homebrew."""
    base = resource_base()
    tess = base / "tesseract" / "tesseract"
    ppm = base / "poppler" / "bin" / "pdftoppm"
    if tess.exists() and ppm.exists():
        tessdata = tess.parent / "tessdata"
        return str(tess), (str(tessdata) if tessdata.exists() else None), str(ppm)
    found_t = shutil.which("tesseract") or next((p for p in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract") if Path(p).exists()), None)
    found_p = shutil.which("pdftoppm") or next((p for p in ("/opt/homebrew/bin/pdftoppm", "/usr/local/bin/pdftoppm") if Path(p).exists()), None)
    return found_t, None, found_p


def _work_dir() -> Path:
    """Where page pictures are made for the reader. Never under /tmp: the
    reader's image library (leptonica) silently rewrites "/tmp/..." paths to
    a different folder on macOS and then can't find the file — which is what
    happens when the app runs without the usual TMPDIR setting."""
    d = Path.home() / "Library" / "Caches" / "Statement Splitter"
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except OSError:
        return Path(tempfile.gettempdir())


def reader_available() -> bool:
    t, _, p = _tools()
    return bool(t and p)


def bill_text(pdf: Path) -> str:
    """The bill's words: its text layer, or text recognition on its first pages."""
    try:
        r = PdfReader(str(pdf))
        text = "\n".join((pg.extract_text() or "") for pg in r.pages[:OCR_PAGES])
        if len(text.strip()) > 40:
            return text
    except Exception:
        pass
    tess, tessdata, ppm = _tools()
    if not (tess and ppm):
        return ""
    env = dict(os.environ)
    if tessdata:
        env["TESSDATA_PREFIX"] = tessdata
    with tempfile.TemporaryDirectory(dir=_work_dir()) as d:
        subprocess.run([ppm, "-r", str(OCR_DPI), "-png", "-l", str(OCR_PAGES), str(pdf), f"{d}/p"],
                       check=True, capture_output=True, timeout=120)
        parts = []
        for img in sorted(Path(d).glob("p*.png")):
            res = subprocess.run([tess, str(img), "stdout", "-l", "eng"], capture_output=True,
                                 timeout=120, env=env)
            # Its messages can contain raw bytes; never let that sink the read.
            parts.append(res.stdout.decode("utf-8", errors="replace"))
        return "\n".join(parts)


# ------------------------------------------------------------------ matching

def _letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _payments(month: dict) -> list[tuple[str, dict, dict]]:
    """(property folder, property data, ledger line) for every bill-like payment."""
    out = []
    for name, p in month["properties"].items():
        for l in p.get("ledger") or []:
            if not l.get("expense"):
                continue
            d = (l.get("description") or "").lower()
            payee = _letters(l.get("payee"))
            if d.startswith(("management fee", "owner distribution")) or "revers" in (l.get("type") or "").lower():
                continue
            if payee.startswith("propertytaxreserve"):
                continue
            out.append((name, p, l))
    return out


@dataclass
class BillResult:
    source: Path
    folder: str                 # property folder, or UNSORTED_NAME
    matched: bool
    reason: str                 # plain English, shown in the window
    payee: str = ""
    amount: float | None = None
    written: Path | None = None


def match_bill(text: str, month: dict) -> tuple[str | None, str, dict | None]:
    """(property folder or None, reason, the matching ledger line or None)."""
    if not text.strip():
        return None, "its text couldn't be read", None
    letters = _letters(text)
    # Whole numbers only — never a run of digits glued across the page, which
    # could "contain" almost any amount by accident.
    amounts = {round(float(a.replace(",", "")), 2) for a in re.findall(r"\d[\d,]*\.\d{2}(?!\d)", text)}
    numbers = {_digits(t) for t in re.findall(r"\d[\d-]*\d|\d", text)}
    cands = [(n, p, l) for n, p, l in _payments(month)
             if len(_letters(l.get("payee"))) >= 5 and _letters(l.get("payee")) in letters]
    if not cands:
        return None, "no payment this month is to a company named on the bill", None
    # The phantom duplicate never wins over a real property.
    real = [c for c in cands if not c[1].get("duplicate")]
    cands = real or cands
    props = {n for n, _, _ in cands}
    if len(props) == 1:
        n, _, l = cands[0]
        return n, f"the only payment to {l['payee']} this month", l

    def score(c) -> int:
        n, p, l = c
        s = 0
        amt = l.get("expense")
        if amt is not None and round(amt, 2) in amounts:
            s += 2
        for m in ACCOUNT_RE.finditer(l.get("description") or ""):
            acct = _digits(m.group(1))
            if len(acct) >= 5 and acct in numbers:
                s += 2
        addr = (p.get("address") or "").split()
        if addr and addr[0].isdigit() and addr[0] in numbers and any(
                len(w) > 3 and _letters(w) in letters for w in addr[1:]):
            s += 1
        return s

    scored = sorted(((score(c), c) for c in cands), key=lambda t: -t[0])
    best = scored[0][0]
    winners = {c[0] for s, c in scored if s == best}
    if best > 0 and len(winners) == 1:
        n, _, l = scored[0][1]
        return n, f"{l['payee']} was paid on several properties; the amount, account or address on the bill points here", l
    names = ", ".join(sorted(props))
    return None, f"{cands[0][2]['payee']} was paid on several properties ({names}) and nothing on the bill tells them apart", None


def file_bills(bills: list[Path], month: dict, destination: Path) -> list[BillResult]:
    destination = Path(destination)
    results = []
    for pdf in bills:
        num = BILL_NAME_RE.match(pdf.name)
        tag = num.group(1) if num else pdf.stem
        try:
            text = bill_text(pdf)
        except Exception as exc:
            text = ""
            why_unread = f"it couldn't be read ({exc})"
        else:
            why_unread = None
        folder, reason, line = match_bill(text, month) if text else (None, why_unread or "its text couldn't be read", None)
        if folder:
            payee = _safe_filename(line["payee"])
            out = destination / folder / f"{month['month']} bill - {payee} ({tag}).pdf"
        else:
            out = destination / UNSORTED_NAME / f"{month['month']} {pdf.stem}.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, out)
        results.append(BillResult(source=pdf, folder=folder or UNSORTED_NAME, matched=bool(folder), reason=reason,
                                  payee=line["payee"] if line else "", amount=line.get("expense") if line else None,
                                  written=out))
    return results
