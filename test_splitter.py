"""Regression test: split both fictional months, then check the comparison.

Run:  python test_splitter.py
"""
import tempfile
from pathlib import Path

from pypdf import PdfReader

import make_sample_packet
from splitter import plan_split, write_split
from summary import update_summary

EXPECTED_AUGUST = [  # (folder name, page count)
    ("004-01 123 Main Street", 4),
    ("004-02 125 Main Street", 4),
    ("004-03 127 Main Street", 4),
    ("004-05 4410 Meadow Lane", 4),
    ("004-06 4412 - 4412 Meadow Lane", 4),
    ("004-07 9 Very Long Address Name Court", 4),
    ("004-01 123 Main Street (duplicate)", 3),
]

# (property, "what" label) that August-vs-July MUST flag as attention
EXPECTED_ATTENTION = {
    ("004-02 125 Main Street", "Rent roll changed"),
    ("004-02 125 Main Street", "Tenant changed"),
    ("004-03 127 Main Street", "Management fee out of line"),
    ("004-06 4412 - 4412 Meadow Lane", "Tenant past due"),
    ("004-06 4412 - 4412 Meadow Lane", "Rent received changed"),
    ("004-07 9 Very Long Address Name Court", "Negative cash balance"),
    ("004-07 9 Very Long Address Name Court", "Reversals don't net to zero"),
    ("004-01 123 Main Street (duplicate)", "Negative cash balance"),
    ("004-01 123 Main Street (duplicate)", "Unit not current"),
}
EXPECTED_NOTES = {
    ("004-05 4410 Meadow Lane", "Charge not seen this month"),   # water bill missing
    ("004-05 4410 Meadow Lane", "New charge"),                    # plumbing repair
    ("004-01 123 Main Street (duplicate)", "New property"),
}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        jul, aug = make_sample_packet.build(tmp / "samples")
        dest = tmp / "out"

        # --- split
        plan = plan_split(aug)
        got = [(s.folder_name, s.page_count) for s in plan.sections]
        assert plan.month == "2026-08" and plan.month_label == "August 2026", (plan.month, plan.month_label)
        assert got == EXPECTED_AUGUST, "\n".join(f"  {g}  vs  {e}" for g, e in zip(got, EXPECTED_AUGUST)) + f"\n({len(got)} sections)"
        assert sum(n for _, n in got) == plan.total_pages
        written = write_split(plan, dest)
        for w in written:
            assert w.path.name == "2026-08.pdf", w.path
            assert len(PdfReader(str(w.path)).pages) == w.section.page_count
        assert any("more than once" in w for w in plan.warnings), plan.warnings

        # --- summary: July first (nothing to compare), then August (compared with July)
        r_jul = update_summary(dest, plan_split(jul), PdfReader(str(jul)))
        assert r_jul.compared_to is None and r_jul.months_on_record == 1
        assert not r_jul.attention, [c.detail for c in r_jul.attention]   # a clean month
        r_aug = update_summary(dest, plan, PdfReader(str(aug)))
        assert r_aug.compared_to == "July 2026" and r_aug.months_on_record == 2
        assert r_aug.workbook.is_file()

        attn = {(c.property, c.what) for c in r_aug.attention}
        notes = {(c.property, c.what) for c in r_aug.notes}
        missing = {e for e in EXPECTED_ATTENTION if e not in attn}
        assert not missing, f"attention items not raised: {missing}\nraised: {sorted(attn)}"
        missing_notes = {e for e in EXPECTED_NOTES if e not in notes}
        assert not missing_notes, f"notes not raised: {missing_notes}\nraised: {sorted(notes)}"
        # Things that must NOT be flagged: the untouched property is quiet on attention.
        assert not [c for c in r_aug.attention if c.property == "004-01 123 Main Street"], \
            [c.detail for c in r_aug.attention if c.property == "004-01 123 Main Street"]
        # A recurring charge with the same amount both months must not read as new/missing.
        noise = [c for c in r_aug.notes if "Waste Management" in c.detail]
        assert not noise, [c.detail for c in noise]

        # --- out of order: August first, then July — the comparison must still be August vs July
        dest2 = tmp / "out2"
        r1 = update_summary(dest2, plan_split(aug), PdfReader(str(aug)))
        assert r1.compared_to is None and r1.ran_is_latest
        r2 = update_summary(dest2, plan_split(jul), PdfReader(str(jul)))
        assert r2.ran_month_label == "July 2026" and not r2.ran_is_latest
        assert r2.month_label == "August 2026" and r2.compared_to == "July 2026", (r2.month_label, r2.compared_to)
        assert {(c.property, c.what) for c in r2.attention} >= EXPECTED_ATTENTION

        # --- ledger reconciles for every property in August
        from ledger import read_property_month
        reader = PdfReader(str(aug))
        for s in plan.sections:
            d = read_property_month(reader, s.first_page, s.last_page)
            inc = sum(l["income"] or 0 for l in d["ledger"]); exp = sum(l["expense"] or 0 for l in d["ledger"])
            assert abs(d["beginning_cash"] + inc - exp - d["ending_cash"]) < 0.011, s.folder_name

    print(f"OK — split {len(EXPECTED_AUGUST)} sections / {plan.total_pages} pages; "
          f"comparison raised {len(r_aug.attention)} attention + {len(r_aug.notes)} notes; ledgers reconcile")


if __name__ == "__main__":
    main()
