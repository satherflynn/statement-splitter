# What's new

## 1.3 — September 29, 2026

- **"What changed" is much shorter.** Bills are now compared with the last
  time *that bill* was paid, not with last month. Garbage and property tax
  are paid quarterly, so the month-to-month comparison was filling the list
  with "new charge" and "not seen this month" lines. A bill is now flagged
  only when its amount differs from its last payment, when it's a genuinely
  new charge on that property, or when it was due by its own rhythm (monthly,
  quarterly) and wasn't paid. The "owner payment changed" lines are gone too;
  they only repeated what the bill lines already said.
- **The "This month" sheet is two tables, one above the other** — income and
  expenses first, then owner payment and balances — with Property and Tenant
  on both, so it fits the screen and reads on a tablet. It also prints on one
  landscape page.
- **Pages that don't belong to any property** (for example, bill copies added
  after the last property's reports) now go to an "Unsorted pages" folder
  with a note, instead of being added to the last property's file.

## 1.2 — September 15, 2026

The app now reads the figures off every page and keeps a **Monthly Summary**
workbook next to the property folders. After each split it tells you what
changed since the previous month on record — rent, tenant, past-due
balances, management fee, charges that appeared, disappeared or changed
amount, reversal entries that don't net to zero, negative balances — and
the workbook holds the full picture: what changed, every property at a
glance, month-by-month history, and a searchable ledger of every
transaction. Signed and notarized by Apple, so it opens with no warning.

## 1.1 — September 15, 2026

Signed with an Apple Developer ID and notarized by Apple, so the app opens
on any Mac with no security warning and no "Open Anyway" step. No change to
how the splitting works.

## 1.0 — September 14, 2026

First release. Splits an AppFolio "Owner Packet" PDF into one file per
property per month, filed as `<code address>/<YYYY-MM>.pdf` inside a folder
of your choice (iCloud Drive › Property Statements by default). Handles
statements that run to a second page, and files a property that appears
twice in one packet under "(duplicate)" so the real one stays clean. Checks
GitHub on launch and offers a Download button when a newer version is out.
