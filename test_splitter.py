"""Regression test: split the fictional sample packet and check every section.

Run:  python test_splitter.py
"""
import tempfile
from pathlib import Path

from pypdf import PdfReader

import make_sample_packet
from splitter import plan_split, write_split

EXPECTED = [  # (folder name, page count)
    ("004-01 123 Main Street", 4),
    ("004-02 125 Main Street", 5),
    ("004-03 127 Main Street", 4),
    ("004-05 4410 Meadow Lane", 4),
    ("004-06 4412 - 4412 Meadow Lane", 4),
    ("004-07 9 Very Long Address Name", 3),
    ("004-08 31 Orchard Court", 4),
    ("004-01 123 Main Street (duplicate)", 3),
]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "sample.pdf"
        make_sample_packet.build(str(src))
        plan = plan_split(src)
        got = [(s.folder_name, s.page_count) for s in plan.sections]
        assert plan.month == "2026-08", plan.month
        assert plan.month_label == "August 2026", plan.month_label
        assert got == EXPECTED, "\n".join(f"  {g}  vs expected  {e}" for g, e in zip(got, EXPECTED)) + f"\n({len(got)} sections)"
        assert sum(n for _, n in got) == plan.total_pages
        written = write_split(plan, tmp / "out")
        assert len(written) == len(EXPECTED)
        for w in written:
            assert w.path.name == "2026-08.pdf", w.path
            assert len(PdfReader(str(w.path)).pages) == w.section.page_count
        assert any("more than once" in w for w in plan.warnings), plan.warnings
    print(f"OK — {len(EXPECTED)} sections, {plan.total_pages} pages, month {plan.month}")


if __name__ == "__main__":
    main()
