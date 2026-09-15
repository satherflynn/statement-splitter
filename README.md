# Statement Splitter

A small Mac app for a landlord whose property manager uses AppFolio. Each
month AppFolio produces one long "Owner Packet" PDF covering every property.
This app splits that packet so each property gets its own file for the
month, filed in its own folder:

```
Property Statements/
  004-01 123 Main Street/
    2026-07.pdf
    2026-08.pdf
  004-02 125 Main Street/
    2026-08.pdf
  …
```

Open a property's folder and every month is side by side, so comparing this
month to last is one click instead of scrolling through 70 pages twice.

## Using it

1. Download the month's statement from AppFolio.
2. Open Statement Splitter, click **Choose PDF…**, pick the file.
3. Click **Split the statement**.

Files go to **iCloud Drive › Property Statements** by default (so an iPad
sees them in the Files app). Change the destination under step 2 in the app;
it's remembered.

Re-running on the same statement simply replaces that month's files.

## How it decides where a page belongs

Every property's section starts with an "Owner Statement" page whose header
carries the code and address (`004 - 01 - 123 Main Street`). The app
starts a new section at each such page, reads the code, and carries it
forward over the Income Statement and Rent Roll pages that follow — including
"Page 2 of 2" continuation pages, which carry no code of their own.

The month comes from the `Period: … - 28 Aug 2026` line printed on every
Owner Statement page, so the file name never depends on the download's name.

If the same code appears twice in one packet (AppFolio can create a phantom
copy of a property by mistake), the first is treated as real and later copies
are filed under `… (duplicate)`.

Pages that come before the first Owner Statement page (a cover letter, say)
are filed under `Unsorted pages/` with the page numbers in the file name.

## Getting the app

The newest build is always at
<https://github.com/satherflynn/statement-splitter/releases/latest> — download
the `.dmg`, open it, drag the app to Applications. The app checks that page
when it opens and shows a Download button if a newer version exists.

## Running from source / building the app

```bash
./Launch\ Statement\ Splitter.command        # run from source (creates venv)
source venv/bin/activate
python splitter.py packet.pdf                # dry run: shows the plan only
python splitter.py packet.pdf ~/out          # …and writes the files
python make_icon.py                          # redraw appicon.icns / .png
rm -rf build "dist/Statement Splitter.app" && python setup.py py2app --no-strip
./build_dmg.sh                               # dist/Statement-Splitter-<version>.dmg + Install Guide
./sign_and_notarize.sh                       # Developer ID signing + Apple notarization (see CLAUDE.md)
```

The `.app` is built standalone (own Python + Tk inside), about 130 MB, so it
opens on a Mac with nothing installed. It is unsigned; the Install Guide in
the DMG covers the one-time "Open Anyway" step.

Never commit a real statement PDF — they contain someone's financial data.
