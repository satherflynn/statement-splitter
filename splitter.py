"""
Core logic for Statement Splitter — no user interface in here.

What it does
------------
AppFolio emails a property manager's client one big "Owner Packet" PDF each
month. Inside, the pages run property by property, and every property's
section always starts with an "Owner Statement" page whose header names the
property with a code and an address, like:

    Properties
    004 - 01 - 123 Main Street
    Somewhere, NV 89000

After that come the Income Statement page(s) and the Rent Roll page. Some
pages (the second page of a long statement, "Page 2 of 2") carry no code at
all, so the splitter can't judge pages one at a time. Instead it:

  1. reads the text of every page,
  2. starts a new section at each "Owner Statement" page,
  3. takes the property code + address from that page,
  4. carries that code forward until the next section starts,
  5. writes each section to  <destination>/<code address>/<YYYY-MM>.pdf

The month comes from the "Period: 28 Jul 2026-28 Aug 2026" line printed on
every Owner Statement page (the END of the period names the month), so the
naming never depends on what the downloaded file happens to be called.

Duplicate codes
---------------
AppFolio once created a phantom copy of a property (same code, address typed
slightly differently). If the same code turns up twice in one packet, the
first occurrence is treated as the real one and every later occurrence is
filed under "<code address> (duplicate)" so nothing gets mixed together.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter

# "004 - 01 - 123 Main Street"   also tolerates   "004-01- 123 Main Street"
CODE_LINE_RE = re.compile(r"^\s*(\d{3})\s*-\s*(\d{2})\s*-\s*(.+?)\s*$")

# "Somewhere, NV 89000" — the city line that ends the address block
CITY_LINE_RE = re.compile(r",\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?\s*$")

# "Period: 28 Jul 2026-28 Aug 2026"  (spacing around the colon/dash varies)
PERIOD_RE = re.compile(
    r"Period:?\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*-\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})"
)
# "As of: Aug 2026"  — fallback if the Period line is ever missing
AS_OF_RE = re.compile(r"As of:?\s*([A-Za-z]{3})\s+(\d{4})")

SECTION_START_MARKER = "Owner Statement"
UNSORTED_NAME = "Unsorted pages"


@dataclass
class Section:
    """One property's run of pages inside the packet."""
    code: str | None            # "004-01"   (None = pages before any section)
    address: str                # "123 Main Street"
    first_page: int             # 1-based, inclusive
    last_page: int              # 1-based, inclusive
    duplicate_of: int = 0       # 0 = first/real occurrence; 1, 2… = later copies

    @property
    def page_count(self) -> int:
        return self.last_page - self.first_page + 1

    @property
    def folder_name(self) -> str:
        if self.code is None:
            return UNSORTED_NAME
        name = f"{self.code} {self.address}".strip()
        if self.duplicate_of:
            suffix = " (duplicate)" if self.duplicate_of == 1 else f" (duplicate {self.duplicate_of})"
            name += suffix
        return _safe_filename(name)


@dataclass
class SplitPlan:
    source: Path
    month: str                  # "2026-08"
    month_label: str            # "August 2026"
    total_pages: int
    sections: list[Section] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    month_guessed: bool = False   # True when no period was printed and we used today's month


@dataclass
class WrittenFile:
    section: Section
    path: Path
    replaced: bool


def _safe_filename(name: str) -> str:
    """Strip characters macOS/iCloud dislike in file names; collapse spaces."""
    name = re.sub(r'[/\\:*?"<>|]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or "Unnamed"


def _month_from_text(text: str) -> tuple[str, str] | None:
    """Return ("2026-08", "August 2026") from a page's text, or None."""
    m = PERIOD_RE.search(text)
    if m:
        for fmt in ("%d %b %Y",):
            try:
                end = datetime.strptime(m.group(2), fmt)
                return end.strftime("%Y-%m"), end.strftime("%B %Y")
            except ValueError:
                pass
    m = AS_OF_RE.search(text)
    if m:
        try:
            d = datetime.strptime(f"1 {m.group(1)} {m.group(2)}", "%d %b %Y")
            return d.strftime("%Y-%m"), d.strftime("%B %Y")
        except ValueError:
            pass
    return None


def _code_from_owner_statement(lines: list[str]) -> tuple[str, str] | None:
    """Find the '004 - 01 - 123 Main Street' line on an Owner Statement page.

    The code line sits just under a line reading 'Properties'; we look there
    first, then anywhere on the page as a fallback.
    """
    order = [i + 1 for i, line in enumerate(lines)
             if line.strip().lower() == "properties" and i + 1 < len(lines)]
    order.extend(range(len(lines)))
    for i in order:
        m = CODE_LINE_RE.match(lines[i])
        if not m:
            continue
        code = f"{m.group(1)}-{m.group(2)}"
        parts = [m.group(3).strip(" -")]
        # A long address wraps onto the next line(s) before the city line
        # ("123 Long Address" / "Ct" / "Somewhere, NV 89000"). Gather the
        # continuation lines until the city/state/zip line or the table starts.
        for j in range(i + 1, min(i + 4, len(lines))):
            nxt = lines[j].strip()
            if not nxt or CITY_LINE_RE.search(nxt) or nxt.startswith("Date "):
                break
            if CODE_LINE_RE.match(nxt):
                break
            parts.append(nxt)
        address = " ".join(parts).strip(" -")
        return code, address
    return None


def plan_split(source: Path) -> SplitPlan:
    """Read the packet and work out which pages belong to which property.

    Nothing is written to disk. The returned plan can be shown to the user
    and then handed to write_split().
    """
    source = Path(source)
    reader = PdfReader(str(source))
    total = len(reader.pages)
    plan = SplitPlan(source=source, month="", month_label="", total_pages=total)

    sections: list[Section] = []
    current: Section | None = None
    seen_codes: dict[str, int] = {}

    for idx in range(total):
        page_no = idx + 1
        try:
            text = reader.pages[idx].extract_text() or ""
        except Exception as exc:  # a damaged page shouldn't sink the whole run
            plan.warnings.append(f"Page {page_no}: could not read its text ({exc}).")
            text = ""
        lines = text.splitlines()
        is_start = any(l.strip() == SECTION_START_MARKER for l in lines)

        if not plan.month:
            found = _month_from_text(text)
            if found:
                plan.month, plan.month_label = found

        if is_start:
            found = _code_from_owner_statement(lines)
            if found:
                code, address = found
            else:
                code, address = None, ""
                plan.warnings.append(
                    f"Page {page_no} looks like an Owner Statement but no property "
                    f"code was found on it; its pages go to '{UNSORTED_NAME}'."
                )
            if current is not None:
                sections.append(current)
            dup = 0
            if code is not None:
                dup = seen_codes.get(code, 0)
                seen_codes[code] = dup + 1
                if dup:
                    plan.warnings.append(
                        f"Property {code} appears more than once in this packet. "
                        f"The copy starting on page {page_no} is filed as "
                        f"'{code} {address} (duplicate)'. The first copy is treated as the real one."
                    )
            current = Section(code=code, address=address, first_page=page_no,
                              last_page=page_no, duplicate_of=dup)
        else:
            if current is None:
                # Pages before the first Owner Statement (cover letter etc.)
                current = Section(code=None, address="", first_page=page_no, last_page=page_no)
            else:
                current.last_page = page_no

    if current is not None:
        sections.append(current)

    plan.sections = sections

    if not plan.month:
        plan.month = datetime.now().strftime("%Y-%m")
        plan.month_label = datetime.now().strftime("%B %Y")
        plan.month_guessed = True
        plan.warnings.append(
            "No statement period was found in the file, so the files are named "
            f"for the current month ({plan.month_label}). Check that this is right."
        )
    if not any(s.code for s in sections):
        plan.warnings.append(
            "No property sections were recognised in this file. Is it an AppFolio "
            "owner packet? (Scanned images can't be read — the text must be selectable.)"
        )
    return plan


def write_split(plan: SplitPlan, destination: Path) -> list[WrittenFile]:
    """Write one PDF per section into <destination>/<folder>/<YYYY-MM>.pdf.

    An existing file for the same property + month is replaced (re-running on
    the same statement is meant to be harmless). Unsorted pages get a file
    name that also says which pages they were, so several stray runs in one
    month don't overwrite each other.
    """
    destination = Path(destination)
    reader = PdfReader(str(plan.source))
    written: list[WrittenFile] = []

    for section in plan.sections:
        folder = destination / section.folder_name
        folder.mkdir(parents=True, exist_ok=True)
        if section.code is None:
            name = f"{plan.month} pages {section.first_page}-{section.last_page}.pdf"
        else:
            name = f"{plan.month}.pdf"
        out_path = folder / name
        replaced = out_path.exists()

        writer = PdfWriter()
        for p in range(section.first_page - 1, section.last_page):
            writer.add_page(reader.pages[p])
        writer.add_metadata({
            "/Title": f"{section.folder_name} — {plan.month_label}",
            "/Producer": "Statement Splitter",
        })
        tmp = out_path.with_suffix(".pdf.partial")
        with open(tmp, "wb") as fh:
            writer.write(fh)
        tmp.replace(out_path)
        written.append(WrittenFile(section=section, path=out_path, replaced=replaced))

    return written


def describe_plan(plan: SplitPlan) -> str:
    """Plain-English summary for the app window (and for the terminal)."""
    lines = [
        f"{plan.source.name}: {plan.total_pages} pages, statement for {plan.month_label}.",
        f"{sum(1 for s in plan.sections if s.code)} property sections found.",
        "",
    ]
    for s in plan.sections:
        pages = (f"page {s.first_page}" if s.page_count == 1
                 else f"pages {s.first_page}–{s.last_page}")
        lines.append(f"  {s.folder_name:<45} {pages} ({s.page_count})")
    if plan.warnings:
        lines.append("")
        lines.append("Please note:")
        for w in plan.warnings:
            lines.append(f"  • {w}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Command-line use (for testing):  python splitter.py packet.pdf [destination]
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    p = plan_split(Path(sys.argv[1]))
    print(describe_plan(p))
    if len(sys.argv) > 2:
        for w in write_split(p, Path(sys.argv[2])):
            print(("replaced " if w.replaced else "wrote    ") + str(w.path))
