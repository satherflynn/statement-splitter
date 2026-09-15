#!/usr/bin/env python3
"""Write the one-page 'Install Guide (Mac).pdf' that ships inside the DMG.

Run:  python make_install_guide.py "Install Guide (Mac).pdf"
"""
import sys
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image

from version import APP_NAME, APP_VERSION

out = sys.argv[1] if len(sys.argv) > 1 else "Install Guide (Mac).pdf"
# Pass --notarized once the build is signed + notarized: the one-time
# "Open Anyway" section then disappears because macOS no longer shows it.
NOTARIZED = "--notarized" in sys.argv[2:]

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=20, leading=26, spaceAfter=6)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=12, spaceAfter=4)
P = ParagraphStyle("p", fontName="Helvetica", fontSize=11, leading=15, spaceAfter=6)
STEP = ParagraphStyle("step", parent=P, leftIndent=18, bulletIndent=2)

doc = SimpleDocTemplate(out, pagesize=LETTER, leftMargin=inch, rightMargin=inch,
                        topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                        title=f"{APP_NAME} — Install Guide", author="Sather Flynn")
story = [
    Image("appicon_128.png", width=0.8 * inch, height=0.8 * inch, hAlign="LEFT"),
    Spacer(1, 6),
    Paragraph(f"{APP_NAME} — Install Guide (Mac)", H1),
    Paragraph(f"Version {APP_VERSION}. Takes about two minutes, once.", P),

    Paragraph("1. Install", H2),
    Paragraph("Open the disk image you were sent (double-click it). A window appears with "
              f"the <b>{APP_NAME}</b> icon and an <b>Applications</b> folder. "
              f"Drag <b>{APP_NAME}</b> onto <b>Applications</b>.", STEP),

    *([] if NOTARIZED else [
        Paragraph("2. First launch (one-time warning)", H2),
        Paragraph("The app isn't registered with Apple's developer program, so the first time you "
                  "open it macOS will say it <i>“cannot be opened because Apple cannot check it "
                  "for malicious software”</i>, or that it is from an unidentified developer. "
                  "This is expected. To get past it:", P),
        Paragraph("• Open <b>System Settings</b> › <b>Privacy &amp; Security</b>.", STEP),
        Paragraph("• Scroll down to the <b>Security</b> section. You'll see a line saying "
                  f"<b>“{APP_NAME}” was blocked</b> with an <b>Open Anyway</b> button. Click it.", STEP),
        Paragraph("• Confirm with your Mac password or Touch ID if asked. The app opens, and "
                  "from then on it opens normally.", STEP),
        Paragraph("If you don't see the Open Anyway button, right-click (or Control-click) the app "
                  "in Applications, choose <b>Open</b>, then click <b>Open</b> in the dialog.", P),
    ]),
    Paragraph("2. Using it each month" if NOTARIZED else "3. Using it each month", H2),
    Paragraph("• Download the month's statement from AppFolio as usual.", STEP),
    Paragraph(f"• Open <b>{APP_NAME}</b>, click <b>Choose PDF…</b>, and pick that file.", STEP),
    Paragraph("• Click <b>Split the statement</b>. Each property's pages are saved as one file "
              "for the month, inside a folder named for that property, in "
              "<b>iCloud Drive › Property Statements</b> (you can change where under step 2 "
              "in the app). The iPad sees the same folders through the Files app.", STEP),
    Paragraph("• To compare months, open a property's folder — every month sits side by side, "
              "named like <b>2026-08.pdf</b>.", STEP),

    Paragraph("Questions", H2),
    Paragraph("Sather Flynn — satherflynn@gmail.com", P),
]
doc.build(story)
print("wrote", out)
