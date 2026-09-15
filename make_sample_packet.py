#!/usr/bin/env python3
"""Build a fictional AppFolio-style owner packet for testing.

Same page structure as the real thing — Owner Statement (sometimes two pages),
Income Statement (sometimes two pages), Rent Roll — with made-up addresses,
tenants and amounts, plus one phantom duplicate property at the end. Lets
anyone try the app, and test_splitter.py, without a real statement.

Run:  python make_sample_packet.py [out.pdf]
"""
import sys
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

PERIOD = "28 Jul 2026-28 Aug 2026"
PROPERTIES = [
    ("004 - 01 - 123 Main Street", 2, 1),      # (code line, owner-statement pages, income pages)
    ("004 - 02 - 125 Main Street", 2, 2),
    ("004 - 03 - 127 Main Street", 2, 1),
    ("004 - 05 - 4410 Meadow Lane", 2, 1),
    ("004 - 06 - 4412 - 4412 Meadow Lane", 2, 1),
    ("004 - 07 - 9 Very Long Address Name", 1, 1),   # wraps onto a second line
    ("004 - 08 - 31 Orchard Court", 1, 2),
    ("004-01- 123 Main Street", 1, 1),          # AppFolio's phantom duplicate
]
CITY = "Somewhere, NV 89000"


def lines(c, ys, rows, x=72, size=10):
    c.setFont("Helvetica", size)
    y = ys
    for r in rows:
        c.drawString(x, y, r)
        y -= 14
    return y


def owner_statement(c, code_line, pages):
    # AppFolio wraps addresses longer than ~30 characters
    addr_lines = [code_line] if len(code_line) <= 30 else [code_line[:30].rstrip(), code_line[30:].strip()]
    lines(c, 740, ["Sample Realty Co.", "1 Manager Way, Suite 100", "Somewhere, NV 89000",
                   f"Period: {PERIOD}", "Owner Statement", "Sample Owner", "P. O. Box 1",
                   "Somewhere, CA 90000", "Properties", *addr_lines, CITY,
                   "Date Payee / Payer Type Reference Description Income Expense Balance",
                   "Beginning Cash Balance as of 07/28/2026 200.00",
                   "08/01/2026 A. Tenant Receipt Rent Income 900.00 1,100.00",
                   "08/03/2026 Sample Realty Co. Check 1001 Management fees 90.00 1,010.00",
                   "08/27/2026 Sample Owner ACH payment Owner Distribution 800.00 210.00",
                   "Ending Cash Balance 210.00", "Total 900.00 890.00",
                   f"Page 1 of {pages}"])
    c.showPage()
    if pages == 2:
        lines(c, 740, ["Bills Due", "Due Date Payee Description Unpaid",
                       "08/01/2026 Property Tax Reserve August 2026 30.00", "Total 30.00",
                       "Property Cash Summary", "Required Reserves 100.00",
                       "Work Order Estimates 0.00", "Page 2 of 2"])
        c.showPage()


def income_statement(c, code_line, pages):
    lines(c, 740, ["Income Statement", "Sample Realty Co.",
                   f"Properties: {code_line} {CITY}", "Owned By: Sample Owner",
                   "As of: Aug 2026", "Level of Detail: Detail View",
                   "Account Name Selected Month % of Selected Month Year to Month End % of Year to Month End",
                   "Income", "Rent Income 900.00 100.00 7,200.00 100.00",
                   "Total Income 900.00 100.00 7,200.00 100.00",
                   "Created on 08/31/2026 Page 1"])
    c.showPage()
    if pages == 2:
        lines(c, 740, ["Income Statement",
                       "Account Name Selected Month % of Selected Month Year to Month End % of Year to Month End",
                       "Net Income 810.00 90.00 6,480.00 90.00", "Created on 08/31/2026 Page 2"])
        c.showPage()


def rent_roll(c, code_line):
    lines(c, 740, ["CORE REVIEW - Rent Roll", f"Properties: {code_line} {CITY}",
                   "Units: Active", "As of: 08/28/2026", "Include Non-Revenue Units: No",
                   "Property Name Unit Tags Tenant Additional Tenants Deposit Rent",
                   "Sample Unit A. Tenant 900.00 900.00", "Total 900.00 900.00"])
    c.showPage()


def build(out):
    c = canvas.Canvas(out, pagesize=LETTER)
    for code_line, os_pages, is_pages in PROPERTIES:
        owner_statement(c, code_line, os_pages)
        income_statement(c, code_line, is_pages)
        rent_roll(c, code_line)
    c.save()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "Sample Owner Packet.pdf"
    build(out)
    print("wrote", out)
