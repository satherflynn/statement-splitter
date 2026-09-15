# CLAUDE.md

Guidance for Claude Code when working in this folder.

## What this is

**Statement Splitter** — a personal favour for a friend of Sather's,
**not an SRF project**. The friend owns rental properties managed through
AppFolio. AppFolio's monthly "Owner Packet" PDF bundles every property; this
app splits it into one file per property per month so months can be compared
easily. The friend uses a Mac and an iPad and shares files through iCloud
Drive, is not technical, and installs from the GitHub release link. (Who the
friend is, and their property details, live in Claude's private memory, not
in this public repository.)

Sather is not a programmer either — describe changes in plain English and
run commands directly.

## Files

- `splitter.py` — all the logic, no UI. `plan_split()` reads the packet and
  returns a `SplitPlan` (sections + month + warnings); `write_split()` writes
  the files; `describe_plan()` renders a plain-English summary. Runnable from
  the terminal for testing (`python splitter.py packet.pdf [dest]`).
- `ledger.py` — reads the *figures* off a property's pages using word
  positions (fixed AppFolio columns; wrapped payees/descriptions are re-joined
  to the nearest dated row). Owner Statement ledger + cash/bills, Income
  Statement totals, Rent Roll (tenant, rent, recurring, past due, status).
- `summary.py` — stores one JSON per month under
  `<dest>/Monthly Summary/data/`, runs the checks (`compare()`), and builds
  `Monthly Summary.xlsx` (What changed / This month / History / Ledger).
  Management fee % is measured against *scheduled* rent (rent roll rent +
  recurring), because the manager charges on scheduled rent whether or not
  the tenant paid. "Section 8 Rent" counts as rent.
- `app.py` — the Tkinter window. Two cards (PDF, destination), one button,
  a results box that shows *what changed* first, then the filing list;
  buttons to open the summary workbook and the folder. Destination remembered
  in `~/Library/Application Support/Statement Splitter/settings.json`.
- `version.py` — `APP_VERSION` (bump with a CHANGELOG entry) + build date.
- `setup.py` — py2app, **standalone** build (bundles Python + Tk).
- `build_dmg.sh` — wraps the .app + Install Guide in a DMG.
- `make_install_guide.py` — the one-page PDF for the first launch (`--notarized` drops the Open-Anyway section).
- `make_icon.py` — draws `appicon.icns` / `appicon_128.png` (teal, fanned pages).
- `update_check.py` — asks GitHub for the latest release on launch; the window
  shows a Download banner if it's newer than `APP_VERSION`. Fails silently offline.
- `sign_and_notarize.sh` + `entitlements.plist` — Developer ID signing and
  Apple notarization of the .app and .dmg (see "Releasing" below).
- `make_sample_packet.py` / `test_splitter.py` — two fictional months (July,
  August) drawn in AppFolio's real column positions with planted differences;
  the test asserts both the split and the comparison flags.

## Releasing a new version

1. Bump `APP_VERSION` in `version.py`, add a section to `CHANGELOG.md`.
2. `rm -rf build dist && python setup.py py2app --no-strip`
3. `./sign_and_notarize.sh` — signs every binary inside the .app with the
   Developer ID Application certificate (Team MW9D3L254H), builds the DMG
   (install guide in `--notarized` form), signs it, submits to Apple's notary
   service (keychain profile `statement-splitter-notary`), staples the ticket.
4. `gh release create v<version> dist/Statement-Splitter-<version>.dmg --title "Statement Splitter <version>" --notes "<what changed>"`
   The permanent link <https://github.com/satherflynn/statement-splitter/releases/latest>
   then serves the new DMG and the in-app update check picks it up.

Signing prerequisites (one-time on Sather's Mac Mini): the Developer ID
Application certificate + private key in the login keychain (private key and
CSR kept in `~/Developer/Signing/`, outside the repo), and notarytool
credentials stored with `xcrun notarytool store-credentials statement-splitter-notary`
(Sather types the app-specific password himself; Claude never handles it).

## How the split works (the part that could break)

Sections start at any page containing a line that is exactly `Owner Statement`.
The property line sits under a `Properties` line: `004 - 01 - 123 Main Street`,
sometimes wrapped onto a second line before the city line (`Somewhere, NV 89000`).
`CODE_LINE_RE` tolerates missing spaces (`004-01- 123 Main Street`, which is
how AppFolio's phantom duplicate was typed). Continuation pages ("Page 2 of 2",
Income Statement page 2) have no code and inherit the current section.

Validated 2026-09-14 against a real August 2026 packet: 69 pages → 17
sections (16 real + one phantom `… (duplicate)`), every page accounted for.
2026-09-15: every real property's ledger reconciled to the cent
(beginning + income − expense = ending) with the position-based reader.
One code number is skipped in the sequence; that's why 17 codes = 16 + 1.
`make_sample_packet.py` builds a fictional packet with the same layout and
`test_splitter.py` checks the split against it — run that after any change.

If AppFolio changes its layout, the first things to check are the
`Owner Statement` marker line and the `Properties` / code line in
`_code_from_owner_statement()`.

## Conventions

- Python 3.13 from python.org (`/Library/Frameworks/Python.framework/Versions/3.13`),
  because Homebrew's Python has no Tk. The venv was created from it.
- Test data (real statements) never live in this repo (`*.pdf` is
  git-ignored) and are deleted from the scratchpad after each session.
- The repo is **public** so the release link works without a GitHub login.
  Keep names, addresses, and the property manager out of every committed file.
- Bundle id `com.satherflynn.statementsplitter`; no SRF naming anywhere.
