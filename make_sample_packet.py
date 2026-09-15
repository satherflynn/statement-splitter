#!/usr/bin/env python3
"""Build fictional AppFolio-style owner packets for testing.

Lays every report out in the same fixed columns AppFolio uses (so ledger.py's
position-based reader is exercised, wrapped payees and all), with made-up
addresses, tenants and amounts. Builds TWO months — July and August — with a
handful of deliberate differences between them so summary.py's comparison has
something to find:

  004-02  rent went up ($900 → $950) and the tenant changed
  004-03  no management fee charged in August (0% — out of line)
  004-05  water bill missing in August; a new "Plumbing repair" charge appears
  004-06  tenant fell $450 past due; rent roll status "Current"
  004-07  reversal entries that don't net to zero; ending cash negative
  phantom duplicate of 004-01 in August only

Run:  python make_sample_packet.py [outdir]     -> Sample Owner Packet July.pdf / August.pdf
"""
import sys
from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

CITY = "Somewhere, NV 89000"
# Column x-positions copied from a real statement.
OS_COLS = {"date": 43, "payee": 90, "type": 173, "ref": 227, "desc": 274, "inc": 487, "exp": 530, "bal": 570}
RR_COLS = {"prop": 39, "unit": 182, "tenant": 235, "extra": 296, "dep": 425, "rent": 470, "rec": 505, "past": 530, "status": 531}

PROPERTIES = [  # code, address, tenant, rent, recurring, deposit
    ("004 - 01", "123 Main Street", "Ann Tenant", 900.00, 21.33, 235.00),
    ("004 - 02", "125 Main Street", "Bob Renter", 900.00, 0.00, 900.00),
    ("004 - 03", "127 Main Street", "Cy Occupant", 900.00, 0.00, 900.00),
    ("004 - 05", "4410 Meadow Lane", "Dee Lessee", 1100.00, 33.77, 700.00),
    ("004 - 06", "4412 - 4412 Meadow Lane", "Ed Dweller", 1100.00, 0.00, 1100.00),
    ("004 - 07", "9 Very Long Address Name Court", "Flo Resident", 800.00, 0.00, 800.00),
]


def rjust_x(c, x_right, text, y, size=9):
    c.setFont("Helvetica", size)
    c.drawRightString(x_right, y, text)


def txt(c, x, y, text, size=9):
    c.setFont("Helvetica", size)
    c.drawString(x, y, text)


def money(v):
    return f"{v:,.2f}"


def owner_statement(c, month, code, addr, ledger, begin, bills_due, page_two=True):
    """ledger: list of (date, payee, type, ref, desc, income, expense). Payee/desc
    longer than the column wraps onto the lines above/below, like AppFolio."""
    y = 726
    txt(c, 40, y, "Sample Realty Co.", 10); txt(c, 410, 721, "Period:"); txt(c, 443, 721, month["period"])
    txt(c, 40, 695, "1 Manager Way, Suite 100"); txt(c, 40, 681, "Somewhere, NV 89000")
    txt(c, 426, 667, "Owner Statement", 11)
    txt(c, 75, 622, "Sample Owner"); txt(c, 424, 622, "Properties")
    if len(addr) > 22:  # wrap the address at a word boundary, like AppFolio does
        cut = addr.rfind(" ", 0, 23)
        txt(c, 424, 607, f"{code} - {addr[:cut]}"); txt(c, 424, 597, addr[cut:].strip()); txt(c, 424, 587, CITY)
    else:
        txt(c, 424, 607, f"{code} - {addr}"); txt(c, 424, 597, CITY)
    y = 500
    for key, label in [("date", "Date"), ("payee", "Payee / Payer"), ("type", "Type"), ("ref", "Reference"),
                       ("desc", "Description")]:
        txt(c, OS_COLS[key] + 2, y, label)
    rjust_x(c, OS_COLS["inc"], "Income", y); rjust_x(c, OS_COLS["exp"], "Expense", y); rjust_x(c, OS_COLS["bal"], "Balance", y)
    y -= 15
    txt(c, OS_COLS["desc"], y, f"Beginning Cash Balance as of {month['begin_date']}"); rjust_x(c, OS_COLS["bal"], money(begin), y)
    bal = begin
    tot_in = tot_out = 0.0
    rows = list(ledger)
    while rows:
        if y < 120:  # continue on page 2
            c.showPage()
            y = 741
            for key, label in [("date", "Date"), ("payee", "Payee / Payer"), ("type", "Type"), ("ref", "Reference"), ("desc", "Description")]:
                txt(c, OS_COLS[key] + 2, y, label)
            rjust_x(c, OS_COLS["inc"], "Income", y); rjust_x(c, OS_COLS["exp"], "Expense", y); rjust_x(c, OS_COLS["bal"], "Balance", y)
        date, payee, typ, ref, desc, inc, exp = rows.pop(0)
        y -= 15
        bal = round(bal + (inc or 0) - (exp or 0), 2); tot_in += inc or 0; tot_out += exp or 0
        txt(c, OS_COLS["date"], y, date)
        pw = payee.split(" ", 1)
        if len(payee) > 16 and len(pw) == 2:      # wrap payee above/below the dated line
            txt(c, OS_COLS["payee"], y + 4.6, pw[0]); txt(c, OS_COLS["payee"], y - 4.6, pw[1])
        else:
            txt(c, OS_COLS["payee"], y, payee)
        tw = typ.split(" ", 1)
        if len(tw) == 2:
            txt(c, OS_COLS["type"], y + 4.6, tw[0]); txt(c, OS_COLS["type"], y - 4.6, tw[1])
        else:
            txt(c, OS_COLS["type"], y, typ)
        txt(c, OS_COLS["ref"], y, ref)
        if len(desc) > 42:   # wrap at a word boundary, as AppFolio does
            cut = desc.rfind(" ", 0, 43)
            txt(c, OS_COLS["desc"], y + 4.6, desc[:cut]); txt(c, OS_COLS["desc"], y - 4.6, desc[cut:].strip())
        else:
            txt(c, OS_COLS["desc"], y, desc)
        if inc: rjust_x(c, OS_COLS["inc"], money(inc), y)
        if exp: rjust_x(c, OS_COLS["exp"], money(exp), y)
        rjust_x(c, OS_COLS["bal"], money(bal), y)
    y -= 15; txt(c, OS_COLS["desc"], y, "Ending Cash Balance"); rjust_x(c, OS_COLS["bal"], money(bal), y)
    y -= 15; txt(c, OS_COLS["date"], y, "Total"); rjust_x(c, OS_COLS["inc"], money(tot_in), y); rjust_x(c, OS_COLS["exp"], money(tot_out), y)
    if page_two:
        c.showPage(); y = 741
    else:
        y -= 30
    txt(c, 40, y, "Bills Due", 10); y -= 26
    txt(c, 45, y, "Due Date"); txt(c, 92, y, "Payee"); txt(c, 331, y, "Description"); txt(c, 476, y, "Unpaid"); y -= 15
    for due, payee, desc, amt in bills_due:
        txt(c, 43, y, due); txt(c, 90, y, payee); txt(c, 329, y, desc); rjust_x(c, 570, money(amt), y); y -= 17
    txt(c, 43, y, "Total"); rjust_x(c, 570, money(sum(b[3] for b in bills_due)), y); y -= 30
    txt(c, 40, y, "Property Cash Summary", 10); y -= 26
    txt(c, 43, y, "Required Reserves"); rjust_x(c, 570, "100.00", y); y -= 15
    txt(c, 43, y, "Work Order Estimates"); rjust_x(c, 570, "0.00", y)
    txt(c, 534, 17, "Page 2 of 2" if page_two else "Page 1 of 1")
    c.showPage()
    return bal


def income_statement(c, month, code, addr, total_income, total_expense, ytd_income, ytd_expense):
    txt(c, 36, 761, "Income Statement", 11); txt(c, 36, 745, "Sample Realty Co.")
    txt(c, 36, 731, "Properties:"); txt(c, 86, 731, f"{code} - {addr} {CITY}")
    txt(c, 36, 717, "Owned By:"); txt(c, 80, 717, "Sample Owner"); txt(c, 36, 703, "As of:"); txt(c, 64, 703, month["as_of"])
    txt(c, 36, 689, "Level of Detail:"); txt(c, 100, 689, "Detail View")
    y = 660
    txt(c, 39, y, "Account Name"); txt(c, 188, y, "Selected Month"); txt(c, 277, y, "% of Selected Month")
    txt(c, 392, y, "Year to Month End"); txt(c, 480, y, "% of Year to Month End"); y -= 20
    net, ynet = total_income - total_expense, ytd_income - ytd_expense
    for label, m, ym in [("Total Operating Income", total_income, ytd_income), ("Total Operating Expense", total_expense, ytd_expense),
                         ("Total Income", total_income, ytd_income), ("Total Expense", total_expense, ytd_expense), ("Net Income", net, ynet)]:
        txt(c, 46, y, label)
        rjust_x(c, 260, money(m), y + 0.2); rjust_x(c, 360, "100.00", y + 0.2); rjust_x(c, 470, money(ym), y + 0.2); rjust_x(c, 570, "100.00", y + 0.2)
        y -= 15
    txt(c, 36, 15, f"Created on {month['created']}"); txt(c, 552, 15, "Page 1")
    c.showPage()


def rent_roll(c, month, code, addr, tenant, rent, recurring, deposit, past_due, status):
    txt(c, 36, 581, "CORE REVIEW - Rent Roll", 11)
    txt(c, 36, 565, "Properties:"); txt(c, 86, 565, f"{code} - {addr} {CITY}")
    txt(c, 36, 551, "Units:"); txt(c, 64, 551, "Active"); txt(c, 36, 537, "As of:"); txt(c, 64, 537, month["as_of_date"])
    txt(c, 36, 496, "Base Report:"); txt(c, 94, 496, "Rent Roll")
    y = 476
    txt(c, 471, 482, "Recurring"); txt(c, 508, 482, "Past")
    for key, label in [("prop", "Property Name"), ("unit", "Unit"), ("tenant", "Tenant"), ("extra", "Additional Tenants")]:
        txt(c, RR_COLS[key], y, label)
    txt(c, 183, y, "Tags")
    rjust_x(c, 425, "Deposit", y); rjust_x(c, 470, "Rent", y); txt(c, 531, y, "Status")
    txt(c, 471, 470, "Charges"); txt(c, 510, 470, "Due")
    y = 455
    txt(c, RR_COLS["prop"], y, code); txt(c, RR_COLS["unit"], y, addr[:10]); txt(c, RR_COLS["unit"], y - 10, addr[10:].strip())
    tw = tenant.split(" ", 1)
    txt(c, RR_COLS["tenant"], y, tw[0]); txt(c, RR_COLS["tenant"], y - 10, tw[1] if len(tw) > 1 else "")
    rjust_x(c, RR_COLS["dep"], money(deposit), y); rjust_x(c, RR_COLS["rent"], money(rent), y)
    rjust_x(c, RR_COLS["rec"], money(recurring), y); rjust_x(c, RR_COLS["past"], money(past_due), y); txt(c, RR_COLS["status"], y, status)
    y = 415
    txt(c, 39, y, "Total"); txt(c, 137, y, "1 Unit"); rjust_x(c, RR_COLS["dep"], money(deposit), y); rjust_x(c, RR_COLS["rent"], money(rent), y)
    rjust_x(c, RR_COLS["rec"], money(recurring), y); rjust_x(c, RR_COLS["past"], money(past_due), y); txt(c, 531, y, "100.0% Occupied")
    txt(c, 36, 15, f"Created on {month['created']}"); txt(c, 732, 15, "Page 1")
    c.showPage()


MONTHS = {
    "july": {"period": "28 Jun 2026-28 Jul 2026", "begin_date": "06/28/2026", "as_of": "Jul 2026",
             "as_of_date": "07/28/2026", "created": "07/31/2026", "d": "07"},
    "august": {"period": "28 Jul 2026-28 Aug 2026", "begin_date": "07/28/2026", "as_of": "Aug 2026",
               "as_of_date": "08/28/2026", "created": "08/31/2026", "d": "08"},
}


def build_month(out: Path, which: str):
    m = MONTHS[which]
    d = m["d"]
    c = canvas.Canvas(str(out), pagesize=LETTER)
    aug = which == "august"
    for code, addr, tenant, rent, recurring, deposit in PROPERTIES:
        past_due, status = 0.00, "Current"
        if aug and code == "004 - 02":
            rent, tenant = 950.00, "Bea Newcomer"
        if aug and code == "004 - 06":
            past_due = 450.00
        fee = round(0.10 * rent, 2)
        if aug and code == "004 - 03":
            fee = 0.0
        led = [
            (f"{d}/01/2026", tenant, "Receipt", "", f"Rent Income - {'August' if aug else 'July'} 2026", rent - (past_due if past_due else 0), None),
        ]
        if recurring:
            led.append((f"{d}/01/2026", tenant, "Receipt", "", "Garbage and Recycling", recurring, None))
        if fee:
            led.append((f"{d}/03/2026", "Sample Realty Co.", "Check", "7742" + d[-1], f"Management fees - Management fees for {d}/2026", None, fee))
        if not (aug and code == "004 - 05"):
            led.append((f"{d}/05/2026", "Somewhere Water Co.", "Payment", "online pay", "Water - 040160-000", None, 61.25))
        if aug and code == "004 - 05":
            led.append((f"{d}/09/2026", "Ace Plumbing Inc.", "Check", "1778" + d[-1], "Plumbing repair - kitchen drain", None, 285.00))
        led.append((f"{d}/11/2026", "Waste Management", "Check", "17742" + d[-1], f"Garbage and Recycling - 6-18078-65003 - {'August' if aug else 'July'} 2026", None, 71.04))
        tax = round(rent * 0.036, 2)
        if aug:
            for mo in ("April", "May", "June", "July"):
                led.append((f"{d}/18/2026", "Property Tax Reserve", "Reversed Check", "177449", f"Property Tax - {mo} 2026", None, tax))
            led.append((f"{d}/18/2026", "Washoe County Treasurer", "Check", "177450", f"Property Tax - 50606103 Aug - August 2026 - 50606103 Aug", None, round(tax * 3.44, 2)))
            months_back = ("April", "May", "June", "July") if code != "004 - 07" else ("April", "May", "June")   # 004-07: one reversal missing
            for mo in months_back:
                led.append((f"{d}/20/2026", "Property Tax Reserve", "Reverse Check", "177449", f"Property Tax - {mo} 2026", tax, None))
        begin = 229.16
        inc = sum(l[5] or 0 for l in led); exp = sum(l[6] or 0 for l in led)
        owner = round(begin + inc - exp - 132.29, 2)
        if aug and code == "004 - 07":
            owner = round(owner + 300.00, 2)   # pays out too much -> negative ending cash
        led.append((f"{d}/27/2026", "Sample Owner", "ACH payment", "", f"Owner Distribution - Owner payment for {d}/2026", None, owner))
        bills = [(f"{d}/01/2026", "Property Tax Reserve", f"{'August' if aug else 'July'} 2026", tax)]
        owner_statement(c, m, code, addr, led, begin, bills, page_two=(len(led) > 9))
        total_income = round(inc, 2); total_expense = round(exp - 0, 2)
        income_statement(c, m, code, addr, total_income, round(fee + 61.25 + 71.04, 2), total_income * (8 if aug else 7), round((fee + 132.29) * (8 if aug else 7), 2))
        rent_roll(c, m, code, addr, tenant, rent, recurring, deposit, past_due, status)
    if aug:  # the phantom duplicate: no activity, negative balance, vacant
        code, addr = "004-01", "123 Main Street"
        owner_statement(c, m, code, addr, [], -105.09, [], page_two=False)
        income_statement(c, m, code, addr, 0.0, 0.0, 0.0, 105.09)
        rent_roll(c, m, code, addr, "", 0.0, 0.0, 0.0, 0.0, "Vacant-Unrented")
    c.save()


def build(outdir: str | Path = ".") -> tuple[Path, Path]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    jul = outdir / "Sample Owner Packet July.pdf"
    aug = outdir / "Sample Owner Packet August.pdf"
    build_month(jul, "july")
    build_month(aug, "august")
    return jul, aug


if __name__ == "__main__":
    for p in build(sys.argv[1] if len(sys.argv) > 1 else "."):
        print("wrote", p)
