"""
Read the numbers off an AppFolio owner packet — one property-month at a time.

splitter.py only needs to know where each property's pages are. This module
goes further and reads what's on them, using the *positions* of the words on
the page rather than the flattened text, because AppFolio lays every report
out in fixed columns:

    Date  Payee / Payer  Type  Reference  Description  Income  Expense  Balance

A long payee or description wraps onto the line just above or just below the
line that carries the date, so we group every fragment with the nearest
dated row and re-join each column top-to-bottom.

Per property-month we collect:
  - the Owner Statement ledger (every transaction),
  - beginning / ending cash, income & expense totals,
  - Bills Due and Required Reserves,
  - Income Statement totals (selected month and year-to-date),
  - Rent Roll: tenant, scheduled rent, deposit, past-due, status.

The result is a plain dict (JSON-friendly) so the app can keep one small
file per month and rebuild the summary workbook from all of them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from pypdf import PdfReader

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
MONEY_RE = re.compile(r"^-?[\d,]*\d\.\d{2}$")
ROW_TOL = 5.5        # points: wrapped lines sit ±4.6 from their dated row
SAME_LINE_TOL = 2.5  # points: values printed a hair above/below their label

OWNER_COLS = ["date", "payee", "type", "reference", "description", "income", "expense", "balance"]


@dataclass
class Frag:
    x: float
    y: float
    text: str


def page_frags(page) -> list[Frag]:
    out: list[Frag] = []

    def visit(text, cm, tm, fd, fs):
        t = text.replace("\n", "").strip()
        if t:
            out.append(Frag(float(tm[4]), float(tm[5]), t))

    page.extract_text(visitor_text=visit)
    return out


def money(s: str | None) -> float | None:
    if not s:
        return None
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _rows(frags: Iterable[Frag], tol: float) -> list[list[Frag]]:
    """Cluster fragments into visual rows (top of page first)."""
    rows: list[list[Frag]] = []
    for f in sorted(frags, key=lambda f: -f.y):
        if rows and abs(rows[-1][0].y - f.y) <= tol:
            rows[-1].append(f)
        else:
            rows.append([f])
    for r in rows:
        r.sort(key=lambda f: f.x)
    return rows


def _find_header(frags: list[Frag], first_label: str, labels: list[str]) -> tuple[float, dict[str, float]] | None:
    """Locate the column header row; return (its y, {column: x})."""
    for f in frags:
        if f.text.strip() == first_label:
            row = [g for g in frags if abs(g.y - f.y) <= SAME_LINE_TOL]
            xs = {}
            for g in row:
                key = g.text.strip().lower()
                for col, lab in zip(OWNER_COLS, labels):
                    if key == lab.lower():
                        xs[col] = g.x
            if len(xs) >= 6:
                return f.y, xs
    return None


def _column_for(x: float, colx: dict[str, float]) -> str:
    """Nearest column by the *midpoints* between header starts — the money
    columns are right-aligned, so their values start well after the header."""
    order = [c for c in OWNER_COLS if c in colx]
    starts = [colx[c] for c in order]
    for i, c in enumerate(order):
        if i + 1 == len(order):
            return c
        mid = (starts[i] + starts[i + 1]) / 2
        if x < mid:
            return c
    return order[-1]


# ---------------------------------------------------------------- Owner Statement

def parse_owner_statement(pages) -> dict:
    """pages: the Owner Statement page(s) of one property (pypdf page objects)."""
    ledger: list[dict] = []
    info = {"beginning_cash": None, "ending_cash": None, "total_income": None,
            "total_expense": None, "bills_due": [], "bills_due_total": None,
            "required_reserves": None, "work_order_estimates": None}

    for page in pages:
        frags = page_frags(page)
        hdr = _find_header(frags, "Date", ["Date", "Payee / Payer", "Type", "Reference",
                                            "Description", "Income", "Expense", "Balance"])
        # Sections below the ledger (a short second page may hold only these).
        bills_y = next((f.y for f in frags if f.text.strip() == "Bills Due"), None)
        cash_y = next((f.y for f in frags if f.text.strip() == "Property Cash Summary"), None)
        ledger_bottom = max([y for y in (bills_y, cash_y) if y is not None] + [-1])

        if hdr:
            hdr_y, colx = hdr
            body = [f for f in frags if f.y < hdr_y - 2 and f.y > ledger_bottom]
        else:
            colx, body = {}, []
        # Anchor rows: dated transactions and the summary lines.
        anchors: list[Frag] = []
        for f in body:
            t = f.text.strip()
            if DATE_RE.match(t) and _column_for(f.x, colx) == "date":
                anchors.append(f)
            elif t.startswith("Beginning Cash Balance") or t.startswith("Ending Cash Balance") or t == "Total":
                anchors.append(f)
        anchors.sort(key=lambda f: -f.y)
        groups: dict[int, list[Frag]] = {i: [] for i in range(len(anchors))}
        for f in body:
            if not anchors:
                break
            i = min(range(len(anchors)), key=lambda i: abs(anchors[i].y - f.y))
            if abs(anchors[i].y - f.y) <= ROW_TOL:
                groups[i].append(f)

        for i, a in enumerate(anchors):
            cols: dict[str, list[Frag]] = {c: [] for c in OWNER_COLS}
            for f in groups[i]:
                cols[_column_for(f.x, colx)].append(f)
            joined = {c: " ".join(g.text.strip() for g in sorted(v, key=lambda g: (-g.y, g.x))).strip()
                      for c, v in cols.items()}
            t = a.text.strip()
            if t.startswith("Beginning Cash Balance"):
                info["beginning_cash"] = money(joined["balance"]) if joined["balance"] else money(_last_money(groups[i]))
                continue
            if t.startswith("Ending Cash Balance"):
                info["ending_cash"] = money(joined["balance"]) if joined["balance"] else money(_last_money(groups[i]))
                continue
            if t == "Total":
                info["total_income"] = money(joined["income"]) or 0.0
                info["total_expense"] = money(joined["expense"]) or 0.0
                continue
            ledger.append({
                "date": joined["date"],
                "payee": joined["payee"],
                "type": joined["type"],
                "reference": joined["reference"],
                "description": joined["description"],
                "income": money(joined["income"]),
                "expense": money(joined["expense"]),
                "balance": money(joined["balance"]),
            })

        # Bills Due table
        if bills_y is not None:
            bottom = cash_y if cash_y is not None else -1
            for row in _rows([f for f in frags if bottom < f.y < bills_y - 2], SAME_LINE_TOL):
                texts = [f.text.strip() for f in row]
                if texts and DATE_RE.match(texts[0]):
                    amt = money(texts[-1]) if MONEY_RE.match(texts[-1]) else None
                    info["bills_due"].append({"due": texts[0], "payee": texts[1] if len(texts) > 2 else "",
                                              "description": " ".join(texts[2:-1]), "amount": amt})
                elif texts and texts[0] == "Total" and len(texts) > 1:
                    info["bills_due_total"] = money(texts[-1])
        if cash_y is not None:
            for row in _rows([f for f in frags if f.y < cash_y - 2], SAME_LINE_TOL):
                texts = [f.text.strip() for f in row]
                if len(texts) >= 2 and texts[0].startswith("Required Reserves"):
                    info["required_reserves"] = money(texts[-1])
                if len(texts) >= 2 and texts[0].startswith("Work Order Estimates"):
                    info["work_order_estimates"] = money(texts[-1])
    if info["bills_due_total"] is None and info["bills_due"]:
        info["bills_due_total"] = round(sum(b["amount"] or 0 for b in info["bills_due"]), 2)
    if info["total_income"] is None:
        info["total_income"] = round(sum(l["income"] or 0 for l in ledger), 2)
    if info["total_expense"] is None:
        info["total_expense"] = round(sum(l["expense"] or 0 for l in ledger), 2)
    if info["ending_cash"] is None and info["beginning_cash"] is not None:
        # A statement with no activity prints no "Ending Cash Balance" line.
        info["ending_cash"] = round(info["beginning_cash"] + info["total_income"] - info["total_expense"], 2)
    info["ledger"] = ledger
    return info


def _last_money(frags: list[Frag]) -> str | None:
    vals = [f.text.strip() for f in sorted(frags, key=lambda f: f.x) if MONEY_RE.match(f.text.strip())]
    return vals[-1] if vals else None


# ---------------------------------------------------------------- Income Statement

def parse_income_statement(pages) -> dict:
    out = {}
    wanted = {"total income": "is_total_income", "total expense": "is_total_expense",
              "net income": "is_net_income", "total operating income": "is_operating_income",
              "total operating expense": "is_operating_expense"}
    for page in pages:
        frags = page_frags(page)
        for row in _rows(frags, SAME_LINE_TOL):
            texts = [f.text.strip() for f in row]
            label = " ".join(t for t in texts if not MONEY_RE.match(t)).strip().lower()
            nums = [money(t) for t in texts if MONEY_RE.match(t)]
            if label in wanted and len(nums) >= 3:
                # Selected month, % of month, year-to-date, % of year
                out[wanted[label]] = nums[0]
                out[wanted[label] + "_ytd"] = nums[2]
    return out


# ---------------------------------------------------------------- Rent Roll

def parse_rent_roll(pages) -> dict:
    units: list[dict] = []
    for page in pages:
        frags = page_frags(page)
        hdr = next((f for f in frags if f.text.strip() == "Property Name"), None)
        if not hdr:
            continue
        row = [g for g in frags if abs(g.y - hdr.y) <= 6]
        colx = {}
        for g in row:
            k = g.text.strip().lower()
            if k in ("property name", "unit", "tags", "tenant", "additional tenants", "deposit", "rent", "status"):
                colx[k] = g.x
        past_due_x = next((g.x for g in row if g.text.strip().lower() == "past"), None)
        rec_x = next((g.x for g in row if g.text.strip().lower() == "recurring"), None)
        total_y = next((f.y for f in frags if f.text.strip() == "Total" and f.x < 60), -1)
        body = [f for f in frags if total_y + 2 < f.y < hdr.y - 8]
        # Unit rows are anchored by a fragment in the Property Name column.
        anchors = sorted([f for f in body if abs(f.x - colx.get("property name", 39)) < 8], key=lambda f: -f.y)
        for a in anchors:
            grp = [f for f in body if abs(f.y - a.y) <= 12 and (f is a or abs(f.x - colx.get("property name", 39)) >= 8)]
            def col_text(x0, x1):
                parts = sorted([f for f in grp if x0 <= f.x < x1], key=lambda f: (-f.y, f.x))
                return " ".join(f.text.strip() for f in parts)
            xs = sorted(colx.values())
            def bounds(key):
                x0 = colx.get(key)
                if x0 is None:
                    return None
                later = [x for x in xs if x > x0]
                return (x0 - 3, (later[0] - 3) if later else 9999)
            def col(key):
                b = bounds(key)
                return col_text(*b) if b else ""
            tenant = col("tenant")
            deposit = money(col_text(colx.get("deposit", 390) - 25, colx.get("rent", 447) - 3)) if "deposit" in colx else None
            rent_txt = col_text(colx.get("rent", 447) - 25, (rec_x or 471) - 3) if "rent" in colx else ""
            rent = money(rent_txt.split()[-1]) if rent_txt else None
            past_due = money(col_text((past_due_x or 508) - 6, colx.get("status", 531) - 3)) if past_due_x else None
            recurring = money(col_text((rec_x or 471) - 3, (past_due_x or 508) - 6)) if rec_x else None
            status = col("status")
            units.append({"unit": col("unit"), "tenant": tenant, "deposit": deposit,
                          "rent": rent, "recurring": recurring, "past_due": past_due, "status": status})
    return {"units": units}


# ---------------------------------------------------------------- one property-month

def page_kind(page) -> str:
    text = page.extract_text() or ""
    lines = [l.strip() for l in text.splitlines()]
    if "Owner Statement" in lines:
        return "owner"
    if any(l.startswith("CORE REVIEW - Rent Roll") for l in lines):
        return "rentroll"
    if lines and lines[0] == "Income Statement":
        return "income"
    if "Page 2 of 2" in lines and not any(l.startswith("Income Statement") for l in lines):
        return "owner"      # continuation of the owner statement
    if any(l.startswith("Account Name") for l in lines):
        return "income"     # continuation of the income statement
    return "other"


def read_property_month(reader: PdfReader, first_page: int, last_page: int) -> dict:
    """Parse one property's section (1-based inclusive page numbers)."""
    groups = {"owner": [], "income": [], "rentroll": [], "other": []}
    for p in range(first_page - 1, last_page):
        page = reader.pages[p]
        groups[page_kind(page)].append(page)
    data = {"pages": last_page - first_page + 1}
    data.update(parse_owner_statement(groups["owner"]))
    data.update(parse_income_statement(groups["income"]))
    data.update(parse_rent_roll(groups["rentroll"]))
    return data


if __name__ == "__main__":
    import json, sys
    from splitter import plan_split
    plan = plan_split(sys.argv[1])
    reader = PdfReader(sys.argv[1])
    which = sys.argv[2:] or [s.folder_name for s in plan.sections]
    for s in plan.sections:
        if s.folder_name in which or s.code in which:
            d = read_property_month(reader, s.first_page, s.last_page)
            print("=" * 70); print(s.folder_name)
            print(json.dumps(d, indent=1))
