---
name: crag-guidebook
description: >-
  Builds a printable rock-climbing crag guidebook (PDF or print-ready HTML) plus KML/GPX/CSV maps
  from every available source: climbing databases such as theCrag, 27crags, UKClimbing and
  Mountain Project, photos of a printed guidebook, local websites and OpenStreetMap. It reconciles
  sources that disagree, works out each sector's aspect and its shade hours (when you can climb),
  adds local-language route names with provenance marks, and collects free topos with credits. It
  revises an existing guide with a visitor's field notes and photos, where observed shade
  overrides the calculation, and rebuilds its crag.json source from a PDF this skill made. Use it
  when someone asks for a guidebook, topo, mini guide, sector guide or crag notes; says "the
  sources disagree, sort them out"; asks when a sector is in the shade or wants the sun hours
  turned into shade hours; hands over photos of a printed guidebook; says "add my notes from my
  visit" or "add the local names of the routes"; or wants to update or fix an old guide.
license: MIT
compatibility: >-
  Python 3.8+ (standard library). Optional: WeasyPrint (PDF output; without it a
  self-contained HTML file is printed to PDF from a browser), PyMuPDF (rebuild from PDF, PDF
  checks), Pillow and pillow-heif (photo GPS, HEIC), matplotlib (plan maps). Web access helps
  for research.
metadata:
  version: 2.0.0
---

# Crag guidebook

Compiling a crag guide is a reconciliation problem wearing a design problem's
clothes. The climbing is documented in four or five places with different sector
names, grading systems, numbering and sector boundaries. Nobody publishes the two
facts people most want — which way a wall faces and **when it is in the shade** — and
the facts that can hurt someone, the state of the bolts, are scattered across warnings
no source aggregates.

So: gather everything, find the key that maps the sources onto each other, calculate
what nobody has written down, add what visitors observed, and lay it out so a climber
can read it at the base of a route.

Run every script from this skill's folder as `python3 scripts/<file>.py`. Each takes
`--help` and prints a JSON summary on stdout; read it rather than assuming success.

## Before anything else (P0)

1. Ask the three questions that change the job:
   - **Which crag, and do they own a printed guidebook?** Photos of its pages are the
     highest-value input: first ascents, local names and real topos exist nowhere else.
   - **When are they going?** Shade is computed for a date; a month is enough.
   - **What do they want out?** A PDF by default; map files, a spreadsheet or only the
     reconciliation report are all valid.
2. Pick the mode (below).
3. If they have a guide whose look they like, read it before designing anything.
4. Check the environment once: can you run Python, and do `weasyprint`, `pymupdf`,
   `PIL` and `matplotlib` import? Tell the user what is missing and what degrades.
   Installing anything is the user's call — ask first.
5. Whenever the user names a folder, file or date, confirm it matches what is actually
   there; people misremember folder names and dates.

## Modes

| Mode | When | Inputs | Output |
|---|---|---|---|
| **A — New guide from sources** | No `crag.json` exists | Crag name; optionally visit month, guidebook photos, a guide they like, a centreline | `crag.json`, guide (PDF or HTML), KML/GPX/CSV, maps, `HANDOVER.md`, decisions log |
| **B — Revise with field notes** | A `crag.json` from this skill + a visitor's notes/photos | Notes, photos, visit date, how to credit the visitor | A new edition (previous kept) with field notes, overrides, photos |
| **C — Rebuild from this skill's PDF** | Only a PDF this skill rendered survives | The PDF, ideally its `*-sectors.csv` | A `crag.json` draft + count report; then continue in B or A |

Routing: `crag.json` from this skill → B. Only a PDF this skill made → C, then B.
Neither → A. A PDF from anywhere else → never parse it; do mode A and treat the PDF
as one more source.

Degraded forms:
- **No guidebook photos:** fewer first ascents, no local topos — say so.
- **No centreline:** fitted axis; every aspect is marked low confidence.
- **No code execution:** deliver the research, the reconciliation report and a
  hand-written `crag.json` only.
- **No WeasyPrint:** the builder writes one self-contained HTML file; give the user
  the print-to-PDF steps (Build, below).
- **No matplotlib:** skip the map pages; the KML still gives the map view.

## Mode A — new guide

### 1. Research, fanned out (P1)
Take one source family per task: theCrag (usually the spine), the local club guide or
site, Mountain Project / UKClimbing / 27crags, local-language news and blogs,
OpenStreetMap. If you can run tasks in parallel, do; otherwise one after another. Each
task reports what it **could not** get as well as what it got. Pace page loads ~10 s
apart; on a 403, read the page as text in a real browser if you have a browser tool.
Coordinates often hide in the page markup — search the raw HTML with a lat/lon regex.
Read `references/sources.md` first.

### 2. Reconcile into one route list (P2)
1. Look for the naming key: online sectors are often named after the printed guide's
   best-known route. Test one pair across the whole list.
2. Confirm matches with first-ascent fingerprints (same equipper and year, whatever
   the transliteration).
3. Splits and merges: print both readings and say which is which.
4. Geography breaks ties: sort sectors along the valley; the order should follow the
   book's numbering.
5. **Verify by counting** (I1): Σ routes = what the spine claims. Put that number in
   `crag.spine_total`.
6. Keep both readings wherever sources disagree (`xref`); never average. Log every
   conflict for the contradictions appendix.
7. Keep the spine's route numbering when you use its topos, so topo numbers match.

Fill `crag.json` as you go — schema in `references/layout.md`, a complete synthetic
example in `examples/crag.json`.

### 3. Photographed guidebook pages (P3)
Read every page image before writing. Take local-script names (exactly as printed),
original grades, first ascents, the local star scale, warnings. Attach each value
through the printed route number stored in `xref` ("Book #N"), never by name
similarity. Crop the topos, credit the book, say "personal use".

### 4. Local-language names (P4)
Fill `local_name` from a source (`local_src: "source"`). Check that a database
actually has local-script names before relying on it. If none has the name but the
Latin name is clearly a transliteration, reconstruct it (`local_src:
"reconstructed"`, printed with †). If unsure, leave it blank and list it in HANDOVER.
Explain † on the How-to-read page; report the tally sourced / reconstructed / blank.

### 5. Topos (P5)
Freely viewable topos only, at the size shown free; never bypass a paywall, login,
bot protection or CDN block. If a site starts refusing, **stop**, record the gap, and
let the user decide. Credit every topo. Save as `topo/<src>_<NN>[a-c].<ext>` and run
`scripts/attach_images.py --crag crag.json --credit "<src>=<caption>"`.

### 6. Aspect and shade (P6)
Run `scripts/crag_conditions.py --crag crag.json --axis file --axis-file axis.json`
(or `--axis auto` / `--axis osm`), with `--horizon` ~25° for a deep gorge, 10–15° for
a valley, 0–5° for an open crag; set `aspect_manual` where the aspect is known. **Keep
the axis file next to `crag.json`.** The guide prints **shade = climbable hours** (the
complement of the sun window within daylight), never "Sun HH:MM–HH:MM", everywhere.
Label every calculated value approximate. Cross-check against every source that
describes conditions. Read `references/conditions.md`.

### 7. Editorial pages (P7)
Write HTML into `front_pages` / `mid_pages` / `back_pages`:
1. **Important before you go** — first front page, `div.imp` numbered list: the
   shade-accuracy caveat (always), crag-wide hazards, anchor type, approach advice,
   crag-wide conditions observations.
2. **About / sources and method** — spine, disagreements and resolutions, sources,
   "what this guide is not", credits and use terms.
3. **How to read** — grades, stars and the top-pick symbol, local names and †,
   warnings and field notes, shade method, cross-check (including any failure).
4. **Crag page** — history, getting there, children, at-a-glance, bolt summary; mark
   it `"approaches": true` so the Approaches box (`crag.approach_tips`) lands there.
5. **Planning** — a `mid_pages` entry with `"generate": "shade_planning"`, plus your
   "if you have one day" and "where to go for what".
6. **Contradictions appendix** — every conflict, including observation vs calculation.
7. **Bolt condition** — each sector flagged / caution / maintained / unknown, with
   counts, and say prominently that **unknown is not a clean bill of health**.
Details in `references/layout.md`; grades, stars, quickdraws and rope in
`references/grades.md`.

### 8. Build (P8)
```bash
python3 scripts/make_maps.py   --crag crag.json --out maps/ --axis-file axis.json --split auto
python3 scripts/export_geo.py  --crag crag.json --out . --slug <crag>
python3 scripts/build_guide.py --crag crag.json --out <crag>.pdf
```
`build_guide.py` refuses to build if an image is missing (it lists them). It uses
WeasyPrint if it imports and renders; otherwise (`ImportError`, `OSError`, any render
error) or with `--force-html` it writes **one self-contained HTML file** (CSS inline,
images embedded). When its JSON says `"renderer": "html"`, tell the user:
1. Open the `.html` file in a browser.
2. Choose **Print**.
3. Set destination **Save as PDF**, paper **A4**, and turn **Background graphics** on.
The HTML contents shows sector numbers instead of page numbers.

Explain the KML rather than apologising for having no satellite image: imported into a
map app it pins every sector on satellite imagery, on a phone.

### 9. Verify (P9)
Run `scripts/verify_guide.py --guide <pdf|html> --crag crag.json` (add `--baseline
old/crag.json` when revising). It checks shade wording, I1–I8, overrides, parking,
Approaches, top pick, Important-first and HTML self-containment. Then **look**: cover,
contents, Important page, a dense and a sparse sector, every sector with field notes
or an override, the index. Check that coordinates plot inside the crag and that derived
numbers (draws, rope) match the prose.

### 10. Handover (P10)
Write `HANDOVER.md` next to the guide and log the user's decisions with dates in
`notes/decisions.md` — templates in `references/handover.md`. Always save `crag.json`,
the axis file and the images next to the guide.

## Mode B — field notes

Read `references/field-notes.md`. In short: set `crag.field_notes_by` and
`field_notes_date`; split the notes into atomic statements and route each — crag-wide
→ Important page / `approach_tips`; sector → `field_notes[]`; route → `field_note`
(opinions on grade or stars go in the note, never over the spine); personal favourite
→ `rating: "top_pick"`; conditions → override or corroboration; parking →
`sector.parking` (from EXIF with `scripts/photo_gps.py`); photos → `topos[]` with
`"photo": true`. Flag fuzzy route matches to the user before writing. Review photos for
plates and faces. Write a new edition (`_v2`), keep the old one, then run steps 6, 8,
9 and 10.

## Mode C — rebuild from PDF

Read `references/rebuild-from-pdf.md`. Confirm the PDF is this skill's house style,
then `python3 scripts/parse_guide_pdf.py --pdf old.pdf --out rebuilt/crag.json
--geo-csv old-sectors.csv`. Check I2 (per-sector counts equal the CSV) — report a
mismatch, never paper over it — and work through the report's review list. State the
limitation: it reads only PDFs this skill rendered with WeasyPrint.

## Judgment calls

- **Observation beats calculation, visibly.** Contradicted → `shade_override`, the
  calculation stays visible marked contradicted, say what was not observed, add an
  appendix row. Agreeing → `conditions_extra`, credited.
- **Shade, not sun.** Print when the wall is climbable; lead with the longer shade
  segment.
- **Always print the accuracy caveat** at the front.
- **Unknown is not fine.** Render unknown bolt state distinctly from maintained.
- **Both readings, one spine.** Never average grades; a visitor's opinion goes in a
  note.
- **† over blank** when the transliteration is clear; **blank over wrong** when not.
- **Free topos only; stop on a block.** The gap is recoverable later.
- **No source file → rebuild it (mode C), never patch the PDF.**
- **Keep the old edition.** New editions get `_v2`, `_v3`.
- **Ask before installing** anything, and before sharing photos with plates or faces.
- `stars: null` = unrated, `0` = rated zero.

## Scripts

| Script | Does | Needs |
|---|---|---|
| `crag_conditions.py` | axis → bank → aspect → sun window; `conditions_meta`; keeps overrides | stdlib |
| `make_maps.py` | scaled plan maps with pins and aspect arrows | matplotlib (optional) |
| `export_geo.py` | KML, GPX, CSV with shade text and parking pins | stdlib |
| `build_guide.py` | `crag.json` → PDF, or self-contained HTML fallback | WeasyPrint (optional) |
| `verify_guide.py` | checklist over the built guide + `crag.json` | PyMuPDF for PDF |
| `parse_guide_pdf.py` | mode C: this skill's PDF → `crag.json` draft | PyMuPDF |
| `photo_gps.py` | EXIF GPS/time from JPG/HEIC; `--to-jpg` | Pillow (+ pillow-heif) |
| `attach_images.py` | add `topo/` and `img/` files by naming convention | stdlib |
| `guide_style.py` | shared style keys and the shade rule (module, not a CLI) | — |

## References

- `references/sources.md` — what each source carries, the reconciliation key,
  provenance, bolt condition, OpenStreetMap centreline, reading printed route tables,
  local names, topo etiquette. Read before research and reconciliation.
- `references/grades.md` — grade conversions, star scales, top pick, quickdraws, rope.
- `references/layout.md` — the `crag.json` schema, page order, editorial pages, the
  HTML fallback, WeasyPrint gotchas, verifying. Read before filling `crag.json`.
- `references/conditions.md` — F1–F3, the shade rule with a worked example, the
  caveat, cross-checking, overrides, the planning page.
- `references/field-notes.md` — mode B in full.
- `references/rebuild-from-pdf.md` — mode C: style keys, parser traps, limitation.
- `references/handover.md` — HANDOVER.md and decisions-log templates.

## Scope

For sport and trad crags documented across several sources — typically a valley or
gorge where aspect follows from the bank. Single walls work with `aspect_manual`. It is
a compilation, not a survey: hazard flags are reproduced because they matter, but their
absence proves nothing — make sure the finished guide says so.
