#!/usr/bin/env python3
"""Generate Dream lo-fi wireframes (Phase 0, Task 3) as SVG.

Grayscale wireframe language:
  outline #94A0AD, fill #E9EDF1 (block) / #F7F9FA (surface), text #46525E,
  accent-dashed = interactive/drag affordance, hatched = image/chart slot.

Run:  python3 generate.py   (writes *.svg beside this file)
"""
from __future__ import annotations
import html
from pathlib import Path

OUT = Path(__file__).parent
INK = "#46525E"; LINE = "#94A0AD"; BLOCK = "#E9EDF1"; SURF = "#F7F9FA"
SOFT = "#DDE4EA"; ACC = "#6B7BD6"

class W:
    def __init__(self, w=1200, h=800, title=""):
        self.w, self.h, self.p = w, h, []
        self.p.append(f'<rect width="{w}" height="{h}" fill="#FFFFFF"/>')
        if title:
            self.text(16, 28, title, size=15, weight="700")
            self.line(16, 40, w - 16, 40)

    def rect(self, x, y, w, h, fill=SURF, stroke=LINE, rx=6, dash=None, sw=1.2):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, size=12, fill=INK, weight="400", anchor="start", mono=False, italic=False):
        fam = "ui-monospace,monospace" if mono else "Inter,system-ui,sans-serif"
        st = ' font-style="italic"' if italic else ""
        self.p.append(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"{st}>{html.escape(s)}</text>')

    def line(self, x1, y1, x2, y2, stroke=LINE, sw=1, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def circle(self, cx, cy, r, fill=BLOCK, stroke=LINE):
        self.p.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}"/>')

    def hatch(self, x, y, w, h, label=""):
        self.rect(x, y, w, h, fill=SURF)
        self.line(x, y, x + w, y + h); self.line(x + w, y, x, y + h)
        if label: self.text(x + w / 2, y + h / 2 - 6, label, anchor="middle", fill=LINE, size=11)

    def pill(self, x, y, s, w=None, fill=BLOCK):
        w = w or (len(s) * 6.4 + 18)
        self.rect(x, y, w, 20, fill=fill, rx=10)
        self.text(x + w / 2, y + 14, s, size=10.5, anchor="middle")
        return w

    def button(self, x, y, s, w=None, primary=False):
        w = w or (len(s) * 6.8 + 26)
        self.rect(x, y, w, 28, fill=SOFT if primary else SURF, rx=6, sw=1.6 if primary else 1.2)
        self.text(x + w / 2, y + 18, s, size=11.5, anchor="middle", weight="600" if primary else "400")
        return w

    def field(self, x, y, w, placeholder):
        self.rect(x, y, w, 30, fill="#FFFFFF")
        self.text(x + 10, y + 19, placeholder, fill=LINE, size=11.5)

    def note(self, x, y, s):
        self.text(x, y, "▸ " + s, fill=ACC, size=10.5, italic=True)

    def rows(self, x, y, w, n, h=30, gap=6, labels=None):
        for i in range(n):
            yy = y + i * (h + gap)
            self.rect(x, yy, w, h, fill=SURF)
            if labels and i < len(labels):
                self.text(x + 10, yy + h / 2 + 4, labels[i], size=11)
        return y + n * (h + gap)

    def save(self, name):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
               f'viewBox="0 0 {self.w} {self.h}">' + "".join(self.p) + "</svg>")
        (OUT / name).write_text(svg, encoding="utf-8")
        print("wrote", name)


def shell(w: W, sidebar=True, sidebar_title="Sessions", rtl=False, y0=56):
    """App shell: title bar, activity rail, optional sidebar, status bar. Returns workspace box."""
    W_, H_ = w.w, w.h
    w.rect(8, y0, W_ - 16, H_ - y0 - 8, fill="#FFFFFF", rx=10, sw=1.4)
    # title bar
    w.rect(8, y0, W_ - 16, 34, fill=SURF, rx=10)
    tb = (W_ - 40) if rtl else 22
    for i, dx in enumerate((0, 18, 36)):
        w.circle((tb + dx) if not rtl else (tb - dx), y0 + 17, 5)
    w.text(W_ / 2, y0 + 21, "Dream — عنوان / Title", size=11, anchor="middle", fill=LINE)
    # activity rail
    rail_x = (W_ - 8 - 48) if rtl else 8
    w.rect(rail_x, y0 + 34, 48, H_ - y0 - 34 - 8 - 24, fill=SURF, rx=0)
    icons = ["Chat", "Proj", "Mem", "Skil", "Sub", "Data", "Prov", "Set"]
    for i, ic in enumerate(icons):
        w.rect(rail_x + 10, y0 + 48 + i * 44, 28, 28, fill=BLOCK, rx=8)
        w.text(rail_x + 24, y0 + 48 + i * 44 + 40, ic, size=8, anchor="middle", fill=LINE)
    # status bar
    w.rect(8, H_ - 8 - 24, W_ - 16, 24, fill=SURF, rx=0)
    sb = [("● Ollama · local", 20), ("net: off", 180), ("2 subagents ▶", 260), ("⌘K palette", W_ - 130)]
    for s, x in sb:
        w.text((W_ - x - 60) if rtl else x, H_ - 8 - 8, s, size=10, fill=LINE)
    # sidebar
    if sidebar:
        sx = (rail_x - 220) if rtl else 56
        w.rect(sx, y0 + 34, 220, H_ - y0 - 34 - 8 - 24, fill=SURF, rx=0)
        w.text(sx + (206 if rtl else 14), y0 + 56, sidebar_title, size=12, weight="700",
               anchor="end" if rtl else "start")
        w.field(sx + 12, y0 + 66, 196, "Search…" if not rtl else "…جستجو")
        wx0 = (56) if rtl else (56 + 220)
        wx1 = (rail_x - 220) if rtl else (W_ - 8)
        return sx, (wx0, y0 + 34, wx1 - wx0, H_ - y0 - 34 - 8 - 24)
    wx0 = 56 if rtl else 56
    return None, ((8 if rtl else 56), y0 + 34, W_ - 16 - 48, H_ - y0 - 34 - 8 - 24)


def transcript(w: W, x, y, wd, compact=False):
    """Draw a conversation transcript with turn anatomy into given area."""
    # user bubble
    w.rect(x + wd - 340, y, 320, 36, fill=BLOCK, rx=10)
    w.text(x + wd - 330, y + 22, "User: summarise this CSV and chart revenue", size=11)
    yy = y + 50
    # context chip
    w.pill(x, yy, "❯ Used 3 memories · 1 reminder  ▾", 230, fill=SURF)
    w.note(x + 240, yy + 14, "collapsible context chip — expands to scored memory list")
    yy += 32
    # tool call card
    w.rect(x, yy, 420, 54, fill=SURF, rx=8)
    w.circle(x + 16, yy + 16, 5, fill=SOFT)
    w.text(x + 28, yy + 20, "read_file(path=…/sales.csv)", size=11, mono=True)
    w.pill(x + 300, yy + 8, "guarded ⛨", 78)
    w.text(x + 28, yy + 40, "status: running ▸ expand for args/result", size=10, fill=LINE)
    yy += 66
    # streaming text
    for i, ln in enumerate([460, 430, 300] if not compact else [300, 260]):
        w.rect(x, yy + i * 16, ln, 9, fill=BLOCK, rx=4, stroke="none")
    w.rect(x + (300 if not compact else 260) + 6, yy + (32 if not compact else 16), 8, 12, fill=ACC, stroke="none")
    w.note(x + 500, yy + 10, "streaming tokens + caret (blink 1s, reduced-motion: steady)")
    yy += (60 if not compact else 44)
    # footer
    w.text(x, yy + 10, "qwen2.5:7b · 4.2s · 812 tok · provenance ↗", size=9.5, fill=LINE)
    return yy + 24


def composer(w: W, x, y, wd):
    w.rect(x, y, wd, 64, fill="#FFFFFF", rx=10, sw=1.4)
    w.text(x + 12, y + 24, "Message Dream…  ( / commands · @ files · ⏎ send · ⇧⏎ newline )", fill=LINE, size=11)
    w.rect(x + wd - 42, y + 16, 32, 32, fill=SOFT, rx=8)
    w.text(x + wd - 26, y + 36, "➤", anchor="middle", size=13)
    w.pill(x + 12, y + 38, "qwen2.5:7b ▾", 90)
    w.pill(x + 110, y + 38, "＋ attach", 64)


# ---------------------------------------------------------------- 01 conversation
w = W(title="3.1 Conversation view — transcript · turn anatomy · composer")
_, (wx, wy, ww, wh) = shell(w)
w.text(wx + 24, wy + 26, "Session: Q3 report analysis", weight="700", size=13)
w.line(wx + 16, wy + 36, wx + ww - 16, wy + 36)
yend = transcript(w, wx + 24, wy + 56, ww - 48)
w.rect(wx + 24, yend + 6, 420, 50, fill=SURF, rx=8)
w.circle(wx + 40, yend + 22, 5, fill=SOFT)
w.text(wx + 52, yend + 26, "search_web(query=…)  → blocked", size=11, mono=True)
w.pill(wx + 324, yend + 14, "dangerous ⛔", 88)
w.note(wx + 460, yend + 30, "blocked card links to approval settings")
composer(w, wx + 24, wy + wh - 90, ww - 48)
w.note(wx + 24, wy + wh - 104, "while streaming: send ➤ becomes Stop ■ (interrupt & redirect)")
# sidebar content
w.text(70, 160, "Today", size=10, weight="700", fill=LINE)
w.rows(68, 168, 196, 2, labels=["Q3 report analysis ●", "گزارش بیمه ماشین"])
w.text(70, 260, "Yesterday", size=10, weight="700", fill=LINE)
w.rows(68, 268, 196, 3, labels=["Trip planning", "Memory cleanup", "CSV import test"])
w.save("01-conversation-view.svg")

# ---------------------------------------------------------------- 02 multi-pane
w = W(title="3.2 Multi-pane layout — 2 / 3 / 4 pane configurations, drag handles")
defs = [("2-pane", [(0, 0, .55, 1, "Conversation"), (.55, 0, .45, 1, "Data grid")]),
        ("3-pane", [(0, 0, .4, 1, "Conversation"), (.4, 0, .6, .55, "Data grid"), (.4, .55, .6, .45, "Chart")]),
        ("4-pane", [(0, 0, .5, .5, "Conversation"), (.5, 0, .5, .5, "Data grid"), (0, .5, .5, .5, "Subagent log"), (.5, .5, .5, .5, "Report")])]
for i, (name, panes) in enumerate(defs):
    X, Y, PW, PH = 30 + i * 390, 80, 360, 250
    w.text(X, Y - 8, name, weight="700", size=13)
    w.rect(X, Y, PW, PH, fill=SURF, rx=8)
    for (px, py, pw_, ph) in [(p[0], p[1], p[2], p[3]) for p in panes]:
        w.rect(X + px * PW + 3, Y + py * PH + 3, pw_ * PW - 6, ph * PH - 6, fill="#FFFFFF", rx=6)
    for p in panes:
        w.text(X + p[0] * PW + 14, Y + p[1] * PH + 24, p[4], size=11, weight="600")
    # drag handles
    if name == "2-pane":
        w.line(X + .55 * PW, Y + 6, X + .55 * PW, Y + PH - 6, stroke=ACC, sw=3, dash="4 4")
w.note(30, 370, "handle: 6px hit area, 1px visible → 3px accent on hover; double-click = equalize; ⌘\\ split, ⌘1..4 focus")
w.text(30, 420, "Pane content types: conversation · data grid · chart · report · file browser · provenance · subagent log", size=12)
w.text(30, 450, "Min pane width 320px — below it, pane collapses to a tab strip on the pane edge", size=12)
w.rect(30, 480, 1140, 260, fill=SURF, rx=10)
w.text(50, 508, "Drag interaction detail", weight="700", size=12)
w.rect(50, 520, 500, 200, fill="#FFFFFF", rx=8)
w.rect(560, 520, 590, 200, fill="#FFFFFF", rx=8)
w.line(555, 520, 555, 720, stroke=ACC, sw=4)
w.text(555, 740, "dragging: live resize (no animation) + width tooltip “420px”", size=10.5, anchor="middle", fill=ACC)
w.save("02-multi-pane.svg")

# ---------------------------------------------------------------- 03 session sidebar
w = W(title="3.3 Session manager sidebar — list · search · date groups · context menu")
_, (wx, wy, ww, wh) = shell(w)
w.text(70, 160, "Pinned", size=10, weight="700", fill=LINE)
w.rows(68, 168, 196, 1, labels=["★ Insurance renewals"])
w.text(70, 226, "Today", size=10, weight="700", fill=LINE)
w.rows(68, 234, 196, 2, labels=["Q3 report ●  (running)", "گزارش بیمه"])
w.text(70, 330, "This week", size=10, weight="700", fill=LINE)
w.rows(68, 338, 196, 4, labels=["Trip planning", "Memory cleanup", "CSV import", "Skill: renewals"])
# context menu
w.rect(290, 240, 180, 176, fill="#FFFFFF", rx=8, sw=1.4)
for j, item in enumerate(["Open", "Open in new pane", "Rename", "Pin", "Move to project ▸", "Export transcript", "— — —", "Delete…"]):
    w.text(304, 262 + j * 20, item, size=11, fill=INK if item != "— — —" else LINE)
w.note(480, 260, "right-click / long-press context menu — every item also in ⌘K palette")
w.note(480, 280, "search = FTS across transcripts, results show session + matching line + summary")
w.text(wx + 60, wy + 60, "Workspace (conversation)", fill=LINE, size=12)
w.rect(wx + 24, wy + 80, ww - 48, wh - 120, fill=SURF, rx=10)
w.save("03-session-sidebar.svg")

# ---------------------------------------------------------------- 04 project dashboard
w = W(title="3.4 Project dashboard — files · sessions · project memory")
_, (wx, wy, ww, wh) = shell(w, sidebar_title="Projects")
w.rows(68, 168, 196, 3, labels=["● Insurance 2026", "Family logistics", "Thesis data"])
w.text(wx + 24, wy + 30, "Insurance 2026", weight="700", size=15)
w.text(wx + 24, wy + 48, "Renew all policies before Mehr — تمدید بیمه", size=11, fill=LINE)
tabs = ["Overview", "Files (4)", "Sessions (7)", "Memory (12)"]
for i, t in enumerate(tabs):
    w.text(wx + 24 + i * 110, wy + 78, t, size=11.5, weight="700" if i == 0 else "400")
w.line(wx + 24, wy + 86, wx + 24 + 110, wy + 86, stroke=INK, sw=2)
w.line(wx + 16, wy + 88, wx + ww - 16, wy + 88)
w.rect(wx + 24, wy + 104, (ww - 72) / 2, 180, fill=SURF, rx=10)
w.text(wx + 40, wy + 128, "Instructions (procedural memory)", weight="700", size=12)
w.rect(wx + 40, wy + 140, (ww - 72) / 2 - 32, 120, fill="#FFFFFF", rx=8)
w.text(wx + 52, wy + 162, "Always quote policy numbers; دو زبانه پاسخ بده…", size=11)
w.rect(wx + 36 + (ww - 72) / 2, wy + 104, (ww - 72) / 2, 180, fill=SURF, rx=10)
w.text(wx + 52 + (ww - 72) / 2, wy + 128, "Recent activity", weight="700", size=12)
w.rows(wx + 52 + (ww - 72) / 2, wy + 140, (ww - 72) / 2 - 32, 4, h=26, labels=["Turn: compared premiums", "Memory added: policy #A-102", "Subagent finished: quotes", "File added: bimeh.pdf"])
w.rect(wx + 24, wy + 300, ww - 48, 150, fill=SURF, rx=10)
w.text(wx + 40, wy + 324, "Files", weight="700", size=12)
w.rows(wx + 40, wy + 336, ww - 80, 3, h=28, labels=["bimeh.pdf · 1.2 MB · added yesterday", "premiums.csv · 88 KB", "letter-draft.md · 4 KB"])
w.button(wx + 24, wy + 470, "＋ New session in project", primary=True)
w.button(wx + 220, wy + 470, "Add files")
w.note(wx + 24, wy + 520, "empty project state: illustration + “Add instructions, files, or start a session”")
w.save("04-project-dashboard.svg")

# ---------------------------------------------------------------- 05 memory explorer
w = W(title="3.5 Memory explorer — list · search · detail · timeline · dedupe")
_, (wx, wy, ww, wh) = shell(w, sidebar_title="Memory")
w.text(70, 170, "Filters", size=10, weight="700", fill=LINE)
for j, f in enumerate(["kind: all ▾", "tags ▾", "importance ≥ 0.5", "date range ▾"]):
    w.pill(68, 180 + j * 28, f, 150)
w.button(68, 310, "Timeline view")
w.button(68, 348, "Dedupe (dry-run)…")
w.note(64, 400, "dedupe: dry-run report modal → owner accepts → apply (house rule)")
lw = (ww - 72) * .5
w.field(wx + 24, wy + 20, lw, "Search memories…  «كتاب» finds «کتاب» (normalized)")
w.note(wx + 24, wy + 66, "result rows show “matched via normalized form” badge when applicable")
labels = [("semantic", "I prefer dark coffee · imp 0.7 · used 12×"),
          ("episodic", "Visited Tehran coffee shop · 3d ago"),
          ("procedural", "Always answer bilingual for insurance"),
          ("semantic", "Policy #A-102 expires Mehr 15 · pinned ★"),
          ("episodic", "Paid premium · 1404/05/20 (Jalali)")]
for i, (kind, txt) in enumerate(labels):
    yy = wy + 80 + i * 44
    w.rect(wx + 24, yy, lw, 38, fill=SURF, rx=8)
    w.pill(wx + 32, yy + 9, kind, 74)
    w.text(wx + 116, yy + 24, txt, size=11)
dx = wx + 40 + lw
w.rect(dx, wy + 80, ww - 48 - lw - 16, 340, fill=SURF, rx=10)
w.text(dx + 16, wy + 104, "Detail — Policy #A-102 expires Mehr 15", weight="700", size=12)
w.rect(dx + 16, wy + 116, ww - 48 - lw - 48, 70, fill="#FFFFFF", rx=8)
w.text(dx + 28, wy + 138, "Full text (editable) · tags: insurance, بیمه", size=11)
for j, meta in enumerate(["importance ▓▓▓▓░ 0.8 (slider)", "used 7× · last used 2d ago", "created 1404/04/02 · بیست تیر", "retrieval score last turn: 0.83"]):
    w.text(dx + 16, wy + 210 + j * 20, meta, size=11, fill=LINE)
w.text(dx + 16, wy + 300, "Turns that used this memory:", size=11, weight="700")
w.rows(dx + 16, wy + 308, ww - 48 - lw - 48, 2, h=24, labels=["“compare premiums” · yesterday ↗", "“when does insurance expire?” · 3d ↗"])
w.rect(wx + 24, wy + 440, ww - 48, 120, fill=SURF, rx=10)
w.text(wx + 40, wy + 464, "Timeline view (episodic) — dual axis Jalali + Gregorian", weight="700", size=12)
w.line(wx + 56, wy + 520, wx + ww - 72, wy + 520, sw=2)
for i in range(6):
    cx = wx + 100 + i * 150
    w.circle(cx, wy + 520, 6, fill=SOFT)
    w.text(cx, wy + 545, f"1404/0{i+2}", size=9, anchor="middle", fill=LINE)
    w.text(cx, wy + 505, ["Apr", "May", "Jun", "Jul", "Aug", "Sep"][i], size=9, anchor="middle", fill=LINE)
w.save("05-memory-explorer.svg")

# ---------------------------------------------------------------- 06 skills manager
w = W(title="3.6 Skills manager — list · detail · enable/disable · import/export")
_, (wx, wy, ww, wh) = shell(w, sidebar_title="Skills")
w.rows(68, 168, 196, 3, labels=["تمدید بیمه ماشین ●", "Monthly report", "Trip checklist (off)"])
w.note(64, 300, "Persian skill names are first-class (RTL rows in LTR shell)")
w.button(68, 320, "＋ New skill", primary=True); w.button(68, 356, "Import .txt"); w.button(68, 392, "Export")
w.text(wx + 24, wy + 30, "تمدید بیمه ماشین", weight="700", size=15)
w.pill(wx + 250, wy + 16, "enabled ✓", 74)
w.text(wx + 24, wy + 52, "Renew car insurance — description shown to the model when matched", size=11, fill=LINE)
w.text(wx + 24, wy + 90, "Steps", weight="700", size=12)
steps = ["Check expiry date memory", "Compare 3 quotes (search_web — guarded)", "Draft renewal letter", "Set reminder for next year (Jalali repeat)"]
for i, s in enumerate(steps):
    w.rect(wx + 24, wy + 100 + i * 40, ww - 460, 34, fill=SURF, rx=8)
    w.text(wx + 36, wy + 122 + i * 40, f"{i+1}. {s}", size=11.5)
w.button(wx + 24, wy + 280, "Edit steps"); w.button(wx + 130, wy + 280, "Run now"); w.button(wx + 224, wy + 280, "Disable")
sx2 = wx + ww - 400
w.rect(sx2, wy + 90, 380, 240, fill=SURF, rx=10)
w.text(sx2 + 16, wy + 114, "Match & usage", weight="700", size=12)
for j, s in enumerate(["score vs “بیمه ماشین”: 0.91", "auto-invoked 4× this month", "last invoked: yesterday ↗ provenance", "save-claim guard: 0 violations"]):
    w.text(sx2 + 16, wy + 140 + j * 22, s, size=11, fill=LINE)
w.note(wx + 24, wy + 360, "empty state: “No skills yet — Dream can learn one after a complex task, or create one”")
w.save("06-skills-manager.svg")

# ---------------------------------------------------------------- 07 provider config
w = W(title="3.7 Model provider configuration — add/edit · API key · test connection")
_, (wx, wy, ww, wh) = shell(w, sidebar=False)
w.rect(wx + 60, wy + 30, ww - 500, 420, fill=SURF, rx=10)
w.text(wx + 80, wy + 58, "Providers", weight="700", size=14)
provs = [("Ollama (local) — default", "● connected · 21ms"), ("OpenAI-compatible", "key stored in OS keychain"), ("Anthropic", "not configured"), ("Offline echo", "always available")]
for i, (nm, st) in enumerate(provs):
    yy = wy + 76 + i * 54
    w.rect(wx + 80, yy, ww - 540, 46, fill="#FFFFFF", rx=8)
    w.text(wx + 96, yy + 20, nm, size=12, weight="600")
    w.text(wx + 96, yy + 36, st, size=10, fill=LINE)
    w.button(wx + ww - 560 - 60, yy + 9, "Edit")
w.button(wx + 80, wy + 300, "＋ Add provider", primary=True)
w.text(wx + 80, wy + 350, "Per-purpose models:", weight="700", size=12)
for j, s in enumerate(["chat: qwen2.5:7b ▾", "subagents: qwen2.5:3b ▾", "extraction: qwen2.5:3b ▾"]):
    w.pill(wx + 80 + j * 170, wy + 362, s, 160)
ex = wx + ww - 420
w.rect(ex, wy + 30, 400, 420, fill="#FFFFFF", rx=10, sw=1.6)
w.text(ex + 20, wy + 58, "Add provider", weight="700", size=13)
w.text(ex + 20, wy + 84, "Type", size=11, fill=LINE); w.field(ex + 20, wy + 92, 360, "OpenAI-compatible ▾")
w.text(ex + 20, wy + 142, "Base URL", size=11, fill=LINE); w.field(ex + 20, wy + 150, 360, "http://localhost:11434/v1")
w.text(ex + 20, wy + 200, "API key", size=11, fill=LINE); w.field(ex + 20, wy + 208, 360, "••••••••••••  (hold to reveal)")
w.text(ex + 20, wy + 258, "Model", size=11, fill=LINE); w.field(ex + 20, wy + 266, 360, "qwen2.5:7b ▾ (fetched on test)")
w.button(ex + 20, wy + 316, "Test connection", primary=True)
w.text(ex + 20, wy + 364, "✓ OK — 21 ms · 4 models found", size=11)
w.note(ex + 20, wy + 386, "before testing, dialog states exactly which host will be contacted (P1 trust)")
w.button(ex + 250, wy + 400, "Save", primary=True); w.button(ex + 170, wy + 400, "Cancel")
w.save("07-provider-config.svg")

# ---------------------------------------------------------------- 08 subagent monitor
w = W(title="3.8 Subagent monitor — dashboard · logs · cancel")
_, (wx, wy, ww, wh) = shell(w, sidebar=False)
cards = [("#3 Research quotes", "running · 02:41 · 12.4k tok", "▶"),
         ("#2 Summarise PDF", "finished ✓ · output ready", "✓"),
         ("#1 Data cleanup", "cancelled · partial log kept", "✕")]
for i, (nm, st, ic) in enumerate(cards):
    x = wx + 40 + i * 300
    w.rect(x, wy + 30, 280, 120, fill=SURF, rx=10)
    w.text(x + 16, wy + 56, nm, weight="700", size=12)
    w.text(x + 16, wy + 76, st, size=10.5, fill=LINE)
    w.text(x + 250, wy + 56, ic, size=14)
    w.text(x + 16, wy + 98, "last: search_web(“بیمه quotes”) → ok", size=9.5, mono=True, fill=LINE)
    w.button(x + 16, wy + 112, "Open log", 80); w.button(x + 106, wy + 112, "Cancel" if i == 0 else "Review", 80)
w.rect(wx + 40, wy + 180, ww - 120, 300, fill="#1E242B", rx=10)
w.text(wx + 60, wy + 206, "Log — Subagent #3 · Research quotes (live, follows tail; scroll up = pause follow)", size=11, fill="#B7C3CE")
logs = ["[12:01:04] turn 1 · plan: find 3 insurers, compare premiums",
        "[12:01:06] [tool] search_web(query='بیمه ماشین قیمت') -> ok",
        "[12:01:09] [tool] read_page(address='https://…') -> ok",
        "[12:01:14] token stream: 'اولین گزینه بیمه…'",
        "[12:01:20] [tool] read_page(…) -> error: timeout — retrying (1/2)"]
for j, ln in enumerate(logs):
    w.text(wx + 60, wy + 232 + j * 20, ln, size=10.5, mono=True, fill="#8BA0B3" if "error" not in ln else "#E5A9A9")
w.rect(wx + 40, wy + 500, ww - 120, 60, fill=SURF, rx=10)
w.text(wx + 60, wy + 524, "Review & accept (finished agents): output summary + artifacts + provenance link →", size=11.5)
w.button(wx + ww - 260, wy + 516, "Accept into conversation", primary=True)
w.note(wx + 40, wy + 590, "empty state: “No subagents yet — ask Dream to work in the background, or use /spawn”; rail icon shows badge count")
w.save("08-subagent-monitor.svg")

# ---------------------------------------------------------------- 09 approval dialog
w = W(title="3.9 Approval dialog — sheet anchored above composer (transcript stays visible)")
_, (wx, wy, ww, wh) = shell(w)
w.rect(wx + 24, wy + 20, ww - 48, 240, fill=SURF, rx=10)
w.text(wx + 40, wy + 45, "…transcript continues behind (not dimmed to black — 20% scrim only)", fill=LINE, size=11)
sx3, sy3, sw3 = wx + ww / 2 - 290, wy + 200, 580
w.rect(sx3, sy3, sw3, 260, fill="#FFFFFF", rx=14, sw=2)
w.pill(sx3 + 20, sy3 + 18, "dangerous ⛔ octagon badge", 170)
w.text(sx3 + 20, sy3 + 62, "Dream wants to send an email", weight="700", size=15)
w.text(sx3 + 20, sy3 + 84, "Tool: send_email — external, irreversible · server: built-in", size=11, fill=LINE)
w.rect(sx3 + 20, sy3 + 96, sw3 - 40, 64, fill=SURF, rx=8)
w.text(sx3 + 32, sy3 + 116, "to: agent@insurer.example — subject: “Renewal request A-102”", size=11, mono=True)
w.text(sx3 + 32, sy3 + 134, "body: 1.2 KB ▸ expand", size=11, mono=True, fill=LINE)
w.text(sx3 + 20, sy3 + 180, "If allowed, this leaves your machine. Deny returns a structured refusal to the model.", size=10.5, fill=LINE)
w.button(sx3 + 20, sy3 + 204, "Deny (Esc)")
w.button(sx3 + 130, sy3 + 204, "Allow once (⏎)", primary=True)
w.button(sx3 + 280, sy3 + 204, "Always allow for this tool…")
w.note(sx3 + 20, sy3 + 248, "“Always allow” opens scope note + adds to Permissions audit list (revocable)")
w.note(wx + 24, sy3 + 290, "motion: sheet slides up 260ms ease-enter; focus trapped; role=alertdialog; announced to screen readers")
composer(w, wx + 24, wy + wh - 90, ww - 48)
w.save("09-approval-dialog.svg")

# ---------------------------------------------------------------- 10 provenance viewer
w = W(title="3.10 Run history / provenance viewer — timeline · artifact tree")
_, (wx, wy, ww, wh) = shell(w, sidebar_title="Runs")
w.rows(68, 168, 196, 4, labels=["#42 Q3 analysis · today", "#41 quotes research", "#40 CSV cleanup", "#39 …"])
w.text(wx + 24, wy + 30, "Run #42 — Q3 analysis", weight="700", size=14)
w.text(wx + 24, wy + 50, "breadcrumb: Runs / #42 / turn 3 / read_file", size=10.5, fill=LINE)
tx = wx + 24
tree = [(0, "Run #42 (session: Q3 report) · 12:01–12:06"),
        (1, "Turn 1 — “summarise this CSV”"),
        (2, "context: 3 memories · 1 reminder"),
        (2, "read_file(sales.csv) → ok"),
        (3, "artifact: table preview #t1"),
        (1, "Turn 2 — “chart revenue”"),
        (2, "run_analysis(step 1..4) → ok"),
        (3, "artifact: chart #c1 (revenue by month)"),
        (3, "artifact: code snippet #s4"),
        (1, "Subagent #3 — quotes research ↗ (linked run)")]
for i, (d, s) in enumerate(tree):
    yy = wy + 76 + i * 32
    w.line(tx + d * 24 + 6, yy - 18, tx + d * 24 + 6, yy + 8, stroke=SOFT)
    w.circle(tx + d * 24 + 6, yy + 4, 4, fill=SOFT)
    w.text(tx + d * 24 + 20, yy + 8, s, size=11.5, mono=(d >= 2))
px = wx + ww - 430
w.rect(px, wy + 76, 410, 330, fill=SURF, rx=10)
w.text(px + 16, wy + 100, "Selected: artifact chart #c1", weight="700", size=12)
w.hatch(px + 16, wy + 112, 378, 180, "chart preview")
for j, s in enumerate(["produced by: run_analysis · turn 2 · step 4", "inputs: sales.csv (sha256 1f0a…) rows 1–840", "open in pane · export PNG/SVG · view code"]):
    w.text(px + 16, wy + 312 + j * 20, s, size=10.5, fill=LINE)
w.button(wx + 24, wy + 420, "Export provenance bundle")
w.button(wx + 230, wy + 420, "Re-run on new file…", primary=True)
w.note(wx + 24, wy + 470, "every transcript message / artifact has “Show provenance” → deep-links to its node here")
w.save("10-provenance-viewer.svg")

# ---------------------------------------------------------------- 11 data science
w = W(title="3.11 Data science workflow — data preview · steps · chart builder · report")
_, (wx, wy, ww, wh) = shell(w, sidebar=False)
gw = ww - 460
w.rect(wx + 30, wy + 20, gw, 300, fill=SURF, rx=10)
w.text(wx + 46, wy + 44, "sales.csv — previewing 10,000 of 1.2M rows (ops run on full file)", size=11, weight="600")
cols = ["date 📅", "region Aa", "revenue #", "notes Aa"]
cw = (gw - 60) / 4
for c, col in enumerate(cols):
    w.rect(wx + 46 + c * cw, wy + 56, cw, 26, fill=SOFT, rx=0)
    w.text(wx + 54 + c * cw, wy + 73, col, size=10.5, weight="700")
for r in range(6):
    for c in range(4):
        yy = wy + 82 + r * 30
        bad = (r == 2 and c == 2) or (r == 4 and c == 0)
        w.rect(wx + 46 + c * cw, yy, cw, 30, fill="#FFF6F6" if bad else "#FFFFFF", rx=0)
        if bad: w.text(wx + 52 + c * cw, yy + 19, "⚠ null", size=9.5, fill="#B04848")
w.note(wx + 46, wy + 290, "issue cells: icon+tint+tooltip (never color alone) · tabular-nums · virtualized")
rx2 = wx + gw + 50
w.rect(rx2, wy + 20, 380, 300, fill=SURF, rx=10)
w.text(rx2 + 16, wy + 44, "Steps (each revertible · provenance nodes)", weight="700", size=11.5)
steps2 = ["1 cast date → datetime ✓", "2 fill nulls revenue=0 ✓", "3 drop col notes ✓", "4 aggregate by month ▶ running", "5 chart revenue/month · queued"]
for j, s in enumerate(steps2):
    w.rect(rx2 + 16, wy + 56 + j * 40, 348, 34, fill="#FFFFFF", rx=8)
    w.text(rx2 + 28, wy + 78 + j * 40, s, size=10.5, mono=True)
    w.text(rx2 + 330, wy + 78 + j * 40, "↩", size=11, fill=LINE)
w.note(rx2 + 16, wy + 270, "‘view code’ per step; agent-made and manual steps are identical objects")
w.rect(wx + 30, wy + 340, (ww - 80) / 2, 220, fill=SURF, rx=10)
w.text(wx + 46, wy + 364, "Chart builder", weight="700", size=12)
for j, s in enumerate(["type: bar ▾", "x: month ▾", "y: revenue ▾", "series: region ▾ (Okabe–Ito palette + patterns)"]):
    w.pill(wx + 46, wy + 376 + j * 28, s, 260)
w.hatch(wx + 330, wy + 376, (ww - 80) / 2 - 320, 160, "live preview")
w.rect(wx + 50 + (ww - 80) / 2, wy + 340, (ww - 80) / 2, 220, fill=SURF, rx=10)
w.text(wx + 66 + (ww - 80) / 2, wy + 364, "Report preview (editable blocks)", weight="700", size=12)
w.rect(wx + 66 + (ww - 80) / 2, wy + 376, (ww - 80) / 2 - 32, 120, fill="#FFFFFF", rx=8)
w.text(wx + 78 + (ww - 80) / 2, wy + 396, "H1 narrative · [chart c1] · table · caption…", size=11, fill=LINE)
w.button(wx + 66 + (ww - 80) / 2, wy + 508, "Export ▾  HTML · PDF · MD (+provenance bundle)", primary=True)
w.save("11-data-science.svg")

# ---------------------------------------------------------------- 12 MCP config
w = W(title="3.12 MCP server configuration — server list · add form · tool list")
_, (wx, wy, ww, wh) = shell(w, sidebar=False)
w.rect(wx + 40, wy + 30, 380, 380, fill=SURF, rx=10)
w.text(wx + 56, wy + 56, "MCP servers", weight="700", size=13)
for i, (nm, st) in enumerate([("filesystem", "● connected · stdio"), ("jalali-tools", "● connected · stdio"), ("web-scraper", "○ error: exited(1) ▸ stderr")]):
    yy = wy + 72 + i * 52
    w.rect(wx + 56, yy, 348, 44, fill="#FFFFFF", rx=8)
    w.text(wx + 70, yy + 19, nm, weight="600", size=12, mono=True)
    w.text(wx + 70, yy + 35, st, size=10, fill=LINE)
w.button(wx + 56, wy + 240, "＋ Add server", primary=True)
fx = wx + 450
w.rect(fx, wy + 30, 330, 380, fill="#FFFFFF", rx=10, sw=1.6)
w.text(fx + 16, wy + 56, "Add server", weight="700", size=12)
w.text(fx + 16, wy + 80, "Name", size=10.5, fill=LINE); w.field(fx + 16, wy + 88, 298, "jalali-tools")
w.text(fx + 16, wy + 134, "Transport", size=10.5, fill=LINE); w.field(fx + 16, wy + 142, 298, "stdio command ▾ | SSE URL")
w.text(fx + 16, wy + 188, "Command", size=10.5, fill=LINE); w.field(fx + 16, wy + 196, 298, "uvx jalali-mcp --locale fa")
w.text(fx + 16, wy + 242, "Env vars", size=10.5, fill=LINE); w.field(fx + 16, wy + 250, 298, "KEY=value (one per line)")
w.button(fx + 16, wy + 300, "Connect & fetch tools", primary=True)
tx2 = fx + 360
w.rect(tx2, wy + 30, ww - (tx2 - wx) - 40, 380, fill=SURF, rx=10)
w.text(tx2 + 16, wy + 56, "Tools from “jalali-tools” (risk override per tool)", weight="700", size=12)
tools = [("jalali_today", "safe ⛨"), ("jalali_convert", "safe ⛨"), ("set_holiday", "guarded ⛨ → override ▾"), ("sync_calendar", "dangerous ⛔ → override ▾")]
for i, (nm, rk) in enumerate(tools):
    yy = wy + 72 + i * 46
    w.rect(tx2 + 16, yy, ww - (tx2 - wx) - 72, 38, fill="#FFFFFF", rx=8)
    w.text(tx2 + 30, yy + 24, nm, size=11.5, mono=True)
    w.pill(tx2 + 220, yy + 9, rk, 170)
    w.pill(tx2 + 400, yy + 9, "on ✓", 46)
w.note(tx2 + 16, wy + 280, "MCP tools carry a server badge everywhere (tool cards, approval sheets, /tools)")
w.note(tx2 + 16, wy + 300, "connection error state shows stderr excerpt / HTTP status inline + retry")
w.save("12-mcp-config.svg")

# ---------------------------------------------------------------- 13 settings
w = W(title="3.13 Settings — all categories (modal ≥ md, full page mobile)")
_, (wx, wy, ww, wh) = shell(w, sidebar=False)
mx, my, mw, mh = wx + 80, wy + 30, ww - 200, wh - 120
w.rect(mx, my, mw, mh, fill="#FFFFFF", rx=14, sw=1.8)
cats = ["General", "Appearance", "Providers", "Integrations", "MCP Servers", "Permissions", "Shortcuts", "About"]
for i, c in enumerate(cats):
    yy = my + 24 + i * 40
    if c == "Appearance": w.rect(mx + 12, yy - 14, 156, 32, fill=BLOCK, rx=8)
    w.text(mx + 26, yy + 6, c, size=12, weight="700" if c == "Appearance" else "400")
w.line(mx + 180, my + 12, mx + 180, my + mh - 12)
cx2 = mx + 210
w.text(cx2, my + 40, "Appearance", weight="700", size=15)
w.text(cx2, my + 78, "Theme", size=12, weight="600")
for j, t in enumerate(["Light", "Dark", "System ✓"]):
    w.rect(cx2 + j * 130, my + 90, 118, 70, fill=SURF, rx=10, sw=1.8 if "✓" in t else 1.2)
    w.text(cx2 + j * 130 + 59, my + 135, t, anchor="middle", size=11)
w.text(cx2, my + 195, "Density", size=12, weight="600")
w.pill(cx2, my + 205, "comfortable ✓", 110); w.pill(cx2 + 120, my + 205, "compact", 90)
w.text(cx2, my + 260, "Font size", size=12, weight="600")
w.rect(cx2, my + 272, 260, 8, fill=SOFT, rx=4); w.circle(cx2 + 140, my + 276, 8, fill="#FFF")
w.text(cx2, my + 320, "Reduce motion", size=12, weight="600")
w.pill(cx2 + 130, my + 306, "follows OS ▾", 100)
w.text(cx2, my + 370, "General (excerpt): language EN/فارسی · calendar Jalali/Gregorian primary · numerals ۱۲۳/123", size=11, fill=LINE)
w.text(cx2, my + 392, "Permissions (excerpt): standing approvals audit list — tool · scope · granted · [Revoke]", size=11, fill=LINE)
w.note(cx2, my + 430, "language change applies instantly + Undo toast 10s (recovery if user can’t read new language)")
w.note(cx2, my + 450, "no setting requires restart; every change confirmed visibly")
w.save("13-settings.svg")

# ---------------------------------------------------------------- 14 file browser
w = W(title="3.14 File browser — tree · preview · context actions")
_, (wx, wy, ww, wh) = shell(w, sidebar_title="Files")
tree2 = ["▾ Insurance 2026/", "   bimeh.pdf", "   premiums.csv ●", "   letter-draft.md", "▸ Thesis data/", "▸ Exports/"]
for j, t in enumerate(tree2):
    w.text(72, 180 + j * 26, t, size=11.5, mono=True, weight="700" if t.startswith("▾") or t.startswith("▸") else "400")
w.rect(290, 250, 170, 130, fill="#FFFFFF", rx=8, sw=1.4)
for j, item in enumerate(["Open in pane", "Preview", "Add to conversation", "Show provenance", "Reveal in OS", "Delete…"]):
    w.text(302, 272 + j * 20, item, size=11)
w.text(wx + 24, wy + 30, "premiums.csv", weight="700", size=14)
w.text(wx + 24, wy + 50, "88 KB · modified yesterday · produced by run #40 step 2 ↗", size=10.5, fill=LINE)
w.rect(wx + 24, wy + 70, ww - 48, 300, fill=SURF, rx=10)
w.text(wx + 40, wy + 94, "Preview (type-aware: table for csv, rendered md, pdf pages, image…)", size=11, fill=LINE)
w.hatch(wx + 40, wy + 106, ww - 80, 240, "csv grid preview")
w.button(wx + 24, wy + 390, "Open in data pane", primary=True)
w.button(wx + 200, wy + 390, "Attach to chat")
w.note(wx + 24, wy + 440, "drag file → onto conversation attaches; onto workspace opens pane; onto project adds to project")
w.save("14-file-browser.svg")

# ---------------------------------------------------------------- 15 onboarding
w = W(title="3.15 Onboarding wizard — 3 steps (first run)")
titles = [("Step 1 — Language & look", ["English (LTR) ●  |  فارسی (RTL) ○", "Theme: Light ○ Dark ○ System ●", "Calendar preview switches live"]),
          ("Step 2 — Choose a provider", ["Ollama (local) — recommended, detected ✓", "OpenAI-compatible / Anthropic (key)", "Offline echo — try Dream with no setup", "→ Test connection inline"]),
          ("Step 3 — Privacy defaults", ["Network tools: off ● on ○", "Approvals: ask every time ●", "Where data lives: ~/.dream (local only)", "→ Finish: land in composer, 3 starter prompts"])]
for i, (t, lines) in enumerate(titles):
    x = 30 + i * 390
    w.rect(x, 80, 360, 420, fill=SURF, rx=14)
    w.text(x + 20, 112, t, weight="700", size=13)
    for j, ln in enumerate(lines):
        w.rect(x + 20, 130 + j * 60, 320, 46, fill="#FFFFFF", rx=8)
        w.text(x + 32, 158 + j * 60, ln, size=10.5)
    for k in range(3):
        w.circle(x + 160 + k * 16, 470, 4, fill=SOFT if k != i else INK)
    w.button(x + 20, 448, "Back" if i else "Skip")
    w.button(x + 250, 448, "Next →" if i < 2 else "Finish ✓", primary=True)
w.note(30, 540, "every step skippable; skipping provider = offline echo + dismissible banner linking to Settings → Providers")
w.note(30, 560, "step transition: slide 320ms ease-standard (mirrored in RTL); reduced-motion: crossfade 0ms")
w.text(30, 610, "Post-onboarding empty conversation:", weight="700", size=12)
w.rect(30, 620, 740, 120, fill=SURF, rx=10)
w.text(50, 648, "“Ask me anything — I remember what matters.”", size=13)
for j, s in enumerate(["Summarise a CSV →", "یادآوری تمدید بیمه →", "What can you do? →"]):
    w.pill(50 + j * 200, 668, s, 180)
w.save("15-onboarding.svg")

# ---------------------------------------------------------------- 16 mobile
w = W(w=1240, h=760, title="3.16 Mobile / tablet web gateway — conversation · sessions · approvals · settings")
screens = [("Conversation", ["◀ Sessions   Q3 report   ⋯", "── streaming turn visible ──", "tool card: read_file → ok", "reply text streams…", "[composer + send, 44px targets]"]),
           ("Sessions", ["Search…", "Today — Q3 report ●", "امروز — گزارش بیمه", "Yesterday — Trip planning", "(status dots = running/pending)"]),
           ("Approvals", ["Pending approval card:", "send_email — dangerous ⛔", "args summary…", "[ Deny ]  [ Allow once ]", "(surfaced as push + badge)"]),
           ("Settings", ["Paired devices · revoke", "Theme · Language فا/EN", "Hand off to desktop →", "Sign out", "(reduced command set = phone)"])]
for i, (t, lines) in enumerate(screens):
    x = 30 + i * 305
    w.rect(x, 70, 270, 560, fill=SURF, rx=24, sw=1.6)
    w.rect(x + 10, 84, 250, 480, fill="#FFFFFF", rx=14)
    w.text(x + 135, 108, t, anchor="middle", weight="700", size=12)
    for j, ln in enumerate(lines):
        w.rect(x + 22, 124 + j * 62, 226, 48, fill=SURF, rx=8)
        w.text(x + 32, 152 + j * 62, ln, size=9.5)
    # bottom tab bar
    w.rect(x + 10, 570, 250, 44, fill=SOFT, rx=10)
    for k, tab in enumerate(["Chat", "Sess", "Appr", "Set"]):
        w.text(x + 42 + k * 62, 597, tab, size=9.5, anchor="middle", weight="700" if k == i else "400")
w.note(30, 668, "breakpoints: <768px single pane + bottom tabs; sidebar becomes sheet; touch targets ≥44px")
w.note(30, 688, "pairing: desktop shows QR + 6-digit code (5 min expiry); device list with revoke on desktop")
w.note(30, 708, "tablet ≥768px: 2-pane (sessions + conversation); approvals as inline sheet like desktop")
w.save("16-mobile-responsive.svg")

# ---------------------------------------------------------------- 17 RTL
w = W(title="3.17 RTL Persian interface — mirrored shell (rail right, sidebar right, composer send at inline-end)")
_, geom = shell(w, sidebar=True, sidebar_title="جلسه‌ها", rtl=True)
wx, wy, ww, wh = geom
w.text(wx + ww - 24, wy + 30, "جلسه: تحلیل گزارش سه‌ماهه", weight="700", size=13, anchor="end")
w.line(wx + 16, wy + 40, wx + ww - 16, wy + 40)
# user bubble at inline-start (left in RTL? no—user bubble at inline-end = left)
w.rect(wx + 24, wy + 60, 320, 36, fill=BLOCK, rx=10)
w.text(wx + 334, wy + 82, "کاربر: این فایل را خلاصه کن", size=11, anchor="end")
w.pill(wx + ww - 254, wy + 110, "▾ ۳ حافظه · ۱ یادآور استفاده شد ❮", 230, fill=SURF)
w.rect(wx + ww - 444, wy + 146, 420, 54, fill=SURF, rx=8)
w.text(wx + ww - 436, wy + 166, "read_file(path=…/sales.csv)", size=11, mono=True)  # LTR island stays LTR
w.note(wx + 24, wy + 172, "tool args = LTR island (dir=ltr, isolate) inside RTL card")
w.pill(wx + ww - 436, wy + 170, "محافظت‌شده ⛨", 90)
for i, ln in enumerate([460, 430, 300]):
    w.rect(wx + ww - 24 - ln, wy + 216 + i * 16, ln, 9, fill=BLOCK, rx=4, stroke="none")
w.text(wx + ww - 24, wy + 292, "qwen2.5:7b · ۴٫۲ ثانیه · ۸۱۲ توکن · پیشینه ↗", size=9.5, fill=LINE, anchor="end")
# composer mirrored
cx3, cy3, cw3 = wx + 24, wy + wh - 90, ww - 48
w.rect(cx3, cy3, cw3, 64, fill="#FFFFFF", rx=10, sw=1.4)
w.text(cx3 + cw3 - 12, cy3 + 24, "…پیامی برای دریم بنویس", fill=LINE, size=11, anchor="end")
w.rect(cx3 + 10, cy3 + 16, 32, 32, fill=SOFT, rx=8)
w.text(cx3 + 26, cy3 + 36, "➤", anchor="middle", size=13)
w.note(cx3, cy3 - 12, "send button at inline-end (= left edge in RTL); punctuation lands correctly (M23 defect fixed structurally)")
# rules panel
w.rect(70, 500, 420, 200, fill=SURF, rx=10)
w.text(86, 526, "Mirroring rules", weight="700", size=12)
rules = ["✓ mirror: rail, sidebar, chevrons, arrows, breadcrumbs, progress fill",
         "✗ keep LTR: code, URLs, API keys, file paths, latency numbers",
         "digits: Persian ۱۲۳ per numerals setting; grids may force Latin",
         "dual dates: ۱۴۰۴/۰۵/۲۴ (2026-08-15) — Jalali primary in FA",
         "text overflow: bidi-isolate every user string in chips/rows"]
for j, r in enumerate(rules):
    w.text(86, 550 + j * 26, r, size=10.5)
w.save("17-rtl-persian.svg")

print("done:", len(list(OUT.glob('*.svg'))), "wireframes")
