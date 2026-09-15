"""
Statement Splitter — the window.

Two choices and one button:
  1. the monthly AppFolio "Owner Packet" PDF,
  2. the folder where the per-property files should go
     (defaults to iCloud Drive › Property Statements so the iPad sees them too),
  then "Split the statement".

All the reading and writing lives in splitter.py; this file only draws the
window and remembers the destination folder between runs.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pypdf import PdfReader

from splitter import plan_split, write_split
from summary import update_summary, SummaryResult, NotSummarised
from update_check import newer_release
from version import APP_NAME, APP_VERSION, resource_base, version_line

SETTINGS_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
ICLOUD_DRIVE = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
DEFAULT_FOLDER_NAME = "Property Statements"

# Colours — deliberately calm; the results box does the talking.
BG = "#f4f6f8"
CARD = "#ffffff"
INK = "#1d2733"
MUTED = "#5f6b78"
ACCENT = "#1e3a5f"       # navy
ACCENT_DARK = "#152a45"
ACCENT_EDGE = "#10213a"
BORDER = "#d9dee4"
BANNER_BG = "#fff7e6"
BANNER_INK = "#7c4a03"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # remembering the folder is a convenience, never a failure


def default_destination() -> Path:
    if ICLOUD_DRIVE.is_dir():
        return ICLOUD_DRIVE / DEFAULT_FOLDER_NAME
    return Path.home() / "Documents" / DEFAULT_FOLDER_NAME


def pretty_path(p: Path) -> str:
    """'iCloud Drive › Property Statements' instead of the raw ~/Library path."""
    try:
        rel = p.relative_to(ICLOUD_DRIVE)
        return "iCloud Drive › " + " › ".join(rel.parts)
    except ValueError:
        pass
    try:
        rel = p.relative_to(Path.home())
        return "Home › " + " › ".join(rel.parts)
    except ValueError:
        return str(p)


class App(tk.Tk):
    def __init__(self, initial_pdf: Path | None = None):
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg=BG)
        self.minsize(660, 600)
        self.geometry("760x680")

        self.settings = load_settings()
        self.source: Path | None = None
        self.destination = Path(self.settings.get("destination") or default_destination())
        self.last_written_folder: Path | None = None
        self._busy = False

        self._build_ui()
        if initial_pdf and initial_pdf.is_file():
            self._set_source(initial_pdf)

    # ---- layout -----------------------------------------------------------
    def _build_ui(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Card.TFrame", background=CARD)
        style.configure("Bg.TFrame", background=BG)
        style.configure("Title.TLabel", background=BG, foreground=INK, font=("Helvetica", 22, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Helvetica", 13))
        style.configure("Step.TLabel", background=CARD, foreground=INK, font=("Helvetica", 14, "bold"))
        style.configure("Value.TLabel", background=CARD, foreground=MUTED, font=("Helvetica", 13))
        style.configure("Foot.TLabel", background=BG, foreground=MUTED, font=("Helvetica", 11))
        style.configure("Action.TButton", font=("Helvetica", 13), padding=(14, 6))
        style.configure("Go.TButton", font=("Helvetica", 15, "bold"), padding=(18, 10),
                        foreground="white", background=ACCENT, borderwidth=0)
        style.map("Go.TButton",
                  background=[("active", ACCENT_DARK), ("disabled", "#9fb3b0")],
                  foreground=[("disabled", "white")])

        outer = ttk.Frame(self, style="Bg.TFrame", padding=(24, 20, 24, 14))
        outer.pack(fill="both", expand=True)

        # Header with the app icon, if we have it.
        head = ttk.Frame(outer, style="Bg.TFrame")
        head.pack(fill="x")
        # Drawn, not a bitmap: Tk paints canvas shapes at full Retina
        # resolution, whereas a small PNG comes out soft on a HiDPI screen.
        self._draw_logo(head, 60).pack(side="left", padx=(0, 14))
        titles = ttk.Frame(head, style="Bg.TFrame")
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        self.subtitle = ttk.Label(titles, style="Sub.TLabel", wraplength=560,
                                  text="Files each property's pages from the monthly AppFolio owner packet, "
                                       "and shows what changed since last month.")
        self.subtitle.pack(anchor="w")

        # Update banner — stays hidden unless GitHub reports a newer release.
        self.banner = tk.Frame(outer, bg=BANNER_BG, padx=14, pady=8,
                               highlightbackground="#f1d9a8", highlightthickness=1)
        self.banner_label = tk.Label(self.banner, bg=BANNER_BG, fg=BANNER_INK,
                                     font=("Helvetica", 12, "bold"), anchor="w")
        self.banner_label.pack(side="left", fill="x", expand=True)
        self.banner_button = ttk.Button(self.banner, text="Download", style="Action.TButton")
        self.banner_button.pack(side="right")
        self._banner_shown = False
        self.after(800, self._start_update_check)

        # Step 1 — the PDF
        c1 = self._card(outer, "1.  The monthly statement")
        self.source_label = ttk.Label(c1, text="No file chosen yet.", style="Value.TLabel", wraplength=560)
        self.source_label.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(c1, text="Choose PDF…", style="Action.TButton", width=13,
                   command=self.choose_pdf).grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
        c1.columnconfigure(0, weight=1)

        # Step 2 — the destination
        c2 = self._card(outer, "2.  Where to file the pages")
        self.dest_label = ttk.Label(c2, text=pretty_path(self.destination), style="Value.TLabel", wraplength=560)
        self.dest_label.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(c2, text="Change…", style="Action.TButton", width=13,
                   command=self.choose_destination).grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
        c2.columnconfigure(0, weight=1)

        # The button
        row = ttk.Frame(outer, style="Bg.TFrame")
        row.pack(fill="x", pady=(14, 10))
        self.go_button = ttk.Button(row, text="Split the statement", style="Go.TButton",
                                    command=self.run_split, state="disabled")
        self.go_button.pack(side="left")
        self.open_button = ttk.Button(row, text="Show the files in Finder", style="Action.TButton",
                                      command=self.open_destination, state="disabled")
        self.open_button.pack(side="right")
        self.summary_button = ttk.Button(row, text="Open the summary workbook", style="Action.TButton",
                                         command=self.open_summary, state="disabled")
        self.summary_button.pack(side="right", padx=(0, 10))
        self.summary_path: Path | None = None

        # Footer goes in first, anchored to the bottom, so a small window can
        # never push it out of view; the results box then takes what's left.
        ttk.Label(outer, text=version_line(), style="Foot.TLabel").pack(side="bottom", anchor="w", pady=(10, 0))

        # Results
        box = tk.Frame(outer, bg=BORDER, padx=1, pady=1)
        box.pack(fill="both", expand=True)
        self.results = tk.Text(box, wrap="word", font=("Helvetica", 13), bg=CARD, fg=INK,
                               relief="flat", padx=14, pady=12, highlightthickness=0,
                               spacing1=2, spacing3=2, cursor="arrow")
        # Readable (selectable, copyable) but not editable: swallow typing.
        self.results.bind("<Key>", lambda e: "break" if not (e.state & 0x8 and e.keysym.lower() == "c") else None)
        scroll = ttk.Scrollbar(box, command=self.results.yview)
        self.results.configure(yscrollcommand=scroll.set)
        self.results.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.results.tag_configure("title", font=("Helvetica", 15, "bold"), spacing3=6)
        self.results.tag_configure("head", font=("Helvetica", 13, "bold"), spacing1=10, spacing3=4)
        self.results.tag_configure("prop", font=("Helvetica", 13, "bold"), lmargin1=14, lmargin2=14, spacing1=6)
        self.results.tag_configure("item", lmargin1=30, lmargin2=44)
        self.results.tag_configure("warn", foreground="#9a3412")
        self.results.tag_configure("warnitem", foreground="#9a3412", lmargin1=30, lmargin2=44)
        self.results.tag_configure("muted", foreground=MUTED)
        self.results.tag_configure("mono", font=("Menlo", 12), lmargin1=14, lmargin2=14)
        self._say("Choose the statement PDF to begin.\n\n"
                  "Each property's pages will be saved as one file per month, inside a folder "
                  "named for that property. The app also reads the figures off every page and "
                  "keeps a Monthly Summary workbook up to date: what changed since last month, "
                  "every property at a glance, month-by-month history, and a searchable ledger.")

        # Long file names / paths wrap to the width actually available.
        self.bind("<Configure>", self._on_resize)

    @staticmethod
    def _draw_logo(parent, size: int) -> tk.Canvas:
        """The app icon as vector shapes: navy rounded square, three fanned pages."""
        import math
        c = tk.Canvas(parent, width=size, height=size, bg=BG, highlightthickness=0, bd=0)
        s = size
        r = s * 0.22
        # Rounded square (four arcs + two rectangles) with a slightly darker edge.
        def rounded(x0, y0, x1, y1, rad, fill):
            c.create_arc(x0, y0, x0 + 2 * rad, y0 + 2 * rad, start=90, extent=90, fill=fill, outline=fill)
            c.create_arc(x1 - 2 * rad, y0, x1, y0 + 2 * rad, start=0, extent=90, fill=fill, outline=fill)
            c.create_arc(x0, y1 - 2 * rad, x0 + 2 * rad, y1, start=180, extent=90, fill=fill, outline=fill)
            c.create_arc(x1 - 2 * rad, y1 - 2 * rad, x1, y1, start=270, extent=90, fill=fill, outline=fill)
            c.create_rectangle(x0 + rad, y0, x1 - rad, y1, fill=fill, outline=fill)
            c.create_rectangle(x0, y0 + rad, x1, y1 - rad, fill=fill, outline=fill)
        rounded(1, 1, s - 1, s - 1, r, ACCENT_EDGE)
        rounded(2, 2, s - 2, s - 2, r - 1, ACCENT)

        def page(cx, cy, w, h, deg, lines=True):
            a = math.radians(deg)
            cos, sin = math.cos(a), math.sin(a)
            def pt(x, y):
                return (cx + x * cos - y * sin, cy + x * sin + y * cos)
            corners = [pt(-w / 2, -h / 2), pt(w / 2, -h / 2), pt(w / 2, h / 2), pt(-w / 2, h / 2)]
            c.create_polygon(*[v for p in corners for v in p], fill="#ffffff", outline="#d7dde6", width=1)
            if lines:
                for i in range(4):
                    y = -h / 2 + h * (0.28 + 0.16 * i)
                    x1 = -w / 2 + w * 0.18
                    x2 = w / 2 - w * (0.18 if i % 3 != 2 else 0.42)
                    c.create_line(*pt(x1, y), *pt(x2, y), fill="#b0becf", width=max(1, s / 40), capstyle="round")
        w, h = s * 0.36, s * 0.46
        page(s * 0.46, s * 0.58, w, h, -14, lines=False)
        page(s * 0.55, s * 0.55, w, h, -4, lines=False)
        page(s * 0.64, s * 0.53, w, h, 7, lines=True)
        return c

    def _on_resize(self, event) -> None:
        if event.widget is not self:
            return
        wrap = max(300, event.width - 300)
        self.source_label.configure(wraplength=wrap)
        self.dest_label.configure(wraplength=wrap)
        self.subtitle.configure(wraplength=max(300, event.width - 160))

    def _card(self, parent, title: str) -> ttk.Frame:
        wrap = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        wrap.pack(fill="x", pady=(14, 0))
        if not hasattr(self, "_first_card_wrap"):
            self._first_card_wrap = wrap
        card = ttk.Frame(wrap, style="Card.TFrame", padding=(16, 12))
        card.pack(fill="x")
        ttk.Label(card, text=title, style="Step.TLabel").grid(row=0, column=0, sticky="w")
        return card

    # ---- actions ----------------------------------------------------------
    def choose_pdf(self) -> None:
        start = self.settings.get("last_source_dir") or str(Path.home() / "Downloads")
        path = filedialog.askopenfilename(
            title="Choose the monthly statement",
            initialdir=start if Path(start).is_dir() else str(Path.home()),
            filetypes=[("PDF files", "*.pdf"), ("All files", "*")],
        )
        if path:
            self._set_source(Path(path))

    def _set_source(self, path: Path) -> None:
        self.source = path
        self.source_label.configure(text=path.name)
        self.go_button.configure(state="normal")
        self.settings["last_source_dir"] = str(path.parent)
        save_settings(self.settings)
        self._say_parts([(f"Ready to split “{path.name}”.\n", "title"),
                         ("Click “Split the statement”.\n", "item")])

    def choose_destination(self) -> None:
        start = self.destination if self.destination.is_dir() else self.destination.parent
        path = filedialog.askdirectory(
            title="Choose where the property folders should go",
            initialdir=str(start) if start.is_dir() else str(Path.home()),
            mustexist=False,
        )
        if path:
            self.destination = Path(path)
            self.dest_label.configure(text=pretty_path(self.destination))
            self.settings["destination"] = str(self.destination)
            save_settings(self.settings)

    def run_split(self) -> None:
        if self._busy or not self.source:
            return
        self._busy = True
        self.go_button.configure(state="disabled", text="Splitting…")
        self._say_parts([("Reading the statement…\n", "title")])
        src, dest = self.source, self.destination

        # The work runs on a helper thread so the window stays responsive;
        # the result comes back through a queue that the main thread polls
        # (Tk widgets must only ever be touched from the main thread).
        outcome: queue.Queue = queue.Queue()

        def work():
            try:
                plan = plan_split(src)
                written = write_split(plan, dest)
                summary = None
                summary_error = None
                try:
                    summary = update_summary(dest, plan, PdfReader(str(src)))
                except NotSummarised as why:   # deliberate skip, with a plain reason
                    summary_error = str(why)
                except Exception:  # the split succeeded; say so, and show why the summary didn't
                    summary_error = traceback.format_exc().strip().splitlines()[-1]
                outcome.put(("ok", plan, written, summary, summary_error))
            except Exception as exc:  # show it, don't die silently
                outcome.put(("error", exc, traceback.format_exc()))

        threading.Thread(target=work, daemon=True).start()
        self._poll(outcome)

    def _poll(self, outcome: "queue.Queue") -> None:
        try:
            result = outcome.get_nowait()
        except queue.Empty:
            self.after(100, lambda: self._poll(outcome))
            return
        if result[0] == "ok":
            self._finish(result[1], result[2], result[3], result[4])
        else:
            self._fail(result[1], result[2])

    def _finish(self, plan, written, summary: "SummaryResult | None", summary_error: str | None) -> None:
        self._busy = False
        self.go_button.configure(state="normal", text="Split the statement")
        self.last_written_folder = self.destination
        self.open_button.configure(state="normal")
        self.settings["destination"] = str(self.destination)
        save_settings(self.settings)

        n_props = sum(1 for w in written if w.section.code)
        n_replaced = sum(1 for w in written if w.replaced)
        lines = [(f"{plan.month_label} is filed.\n", "title"),
                 (f"{plan.total_pages} pages went into {n_props} property folder{'s' if n_props != 1 else ''} "
                  f"in {pretty_path(self.destination)}.\n", "muted")]

        # --- What changed (the useful part) goes first.
        if summary is not None:
            self.summary_path = summary.workbook
            self.summary_button.configure(state="normal")
            if not summary.ran_is_latest:
                lines.append((f"You ran {summary.ran_month_label}, which is earlier than the latest month on record, "
                              f"so it has been added to the history. The comparison below is for "
                              f"{summary.month_label}, the latest month.\n", "muted"))
            if summary.compared_to:
                lines.append((f"What changed — {summary.month_label} compared with {summary.compared_to}\n", "head"))
                if not summary.changes:
                    lines.append(("Nothing stood out. Every figure matches last month.\n", "item"))
            else:
                lines.append((f"What stands out in {summary.month_label}\n", "head"))
                lines.append(("This is the first month on record, so there is nothing to compare against yet. "
                              "Run last month's statement and the comparison fills in. "
                              "The checks below don't need a prior month.\n", "item"))
            if summary.attention:
                lines.append((f"Needs a look ({len(summary.attention)})\n", "warn"))
                lines.extend(self._grouped(summary.attention, "warnitem"))
            if summary.notes:
                lines.append((f"Smaller differences ({len(summary.notes)})\n", "head"))
                lines.extend(self._grouped(summary.notes, "item"))
            lines.append((f"The full picture is in the Monthly Summary workbook ({summary.months_on_record} "
                          f"month{'s' if summary.months_on_record != 1 else ''} on record): what changed, every "
                          "property at a glance, month-by-month history, and a searchable ledger.\n", "muted"))
        elif summary_error:
            lines.append(("The pages were filed, but the Monthly Summary was not updated.\n", "head"))
            lines.append((summary_error + "\n", "warnitem"))

        lines.append(("Filed\n", "head"))
        for w in written:
            s = w.section
            pages = f"{s.page_count} page{'s' if s.page_count != 1 else ''}"
            note = "   (replaced last copy)" if w.replaced else ""
            lines.append((f"{s.folder_name}  ›  {w.path.name}   {pages}{note}\n", "mono" if s.code else "warnitem"))
        if n_replaced:
            lines.append((f"{n_replaced} file{'s' if n_replaced != 1 else ''} for this month "
                          "already existed and were replaced with this copy.\n", "muted"))
        if plan.warnings:
            lines.append(("Please note\n", "head"))
            for wmsg in plan.warnings:
                lines.append((f"{wmsg}\n", "warnitem"))
        self._say_parts(lines)

    @staticmethod
    def _grouped(changes, item_tag: str) -> list[tuple[str, str]]:
        """Property name once, then its items indented beneath it."""
        out: list[tuple[str, str]] = []
        current = None
        for c in changes:
            if c.property != current:
                current = c.property
                out.append((f"{c.property}\n", "prop"))
            out.append((f"• {c.detail}\n", item_tag))
        return out

    def _fail(self, exc: Exception, detail: str) -> None:
        self._busy = False
        self.go_button.configure(state="normal", text="Split the statement")
        self._say_parts([("Something went wrong.\n", "title"),
                         (f"{exc}\n", "warnitem"),
                         ("If this keeps happening, select the text in this box, copy it, "
                          "and send it to Sather along with the PDF you were trying to split.\n", "item"),
                         (detail, "mono")])
        messagebox.showerror(APP_NAME, f"The statement could not be split.\n\n{exc}")

    def open_summary(self) -> None:
        if self.summary_path and self.summary_path.is_file():
            subprocess.Popen(["open", str(self.summary_path)])

    def open_destination(self) -> None:
        folder = self.last_written_folder or self.destination
        if folder.is_dir():
            subprocess.Popen(["open", str(folder)])

    # ---- update check -----------------------------------------------------
    def _start_update_check(self) -> None:
        result: queue.Queue = queue.Queue()
        threading.Thread(target=lambda: result.put(newer_release()), daemon=True).start()
        self._poll_update(result)

    def _poll_update(self, result: "queue.Queue") -> None:
        try:
            found = result.get_nowait()
        except queue.Empty:
            self.after(200, lambda: self._poll_update(result))
            return
        if found:
            self._show_update_banner(*found)

    def _show_update_banner(self, version: str, page_url: str) -> None:
        if self._banner_shown:
            return
        self._banner_shown = True
        self.banner_label.configure(
            text=f"Version {version} is available. You have {APP_VERSION}.")
        self.banner_button.configure(command=lambda: webbrowser.open(page_url))
        # Slot the banner just above the first card.
        self.banner.pack(fill="x", pady=(14, 0), before=self._first_card_wrap)

    # ---- results box helpers ---------------------------------------------
    def _say(self, text: str) -> None:
        self._say_parts([(text, "")])

    def _say_parts(self, parts) -> None:
        self.results.delete("1.0", "end")
        for text, tag in parts:
            if tag:
                self.results.insert("end", text, tag)
            else:
                self.results.insert("end", text)
        self.results.see("1.0")


def main() -> None:
    initial = None
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".pdf"):
            initial = Path(arg)
            break
    app = App(initial)
    app.mainloop()


if __name__ == "__main__":
    main()
