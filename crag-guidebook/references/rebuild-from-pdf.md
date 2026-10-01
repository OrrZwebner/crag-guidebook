# Mode C — rebuilding crag.json from a guide PDF this skill made

Read this when a guide exists only as a PDF and it needs revising (procedure PC).
Never patch the PDF: table-wide changes (shade wording, local names) need a source.

## Limitation — state it to the user

`parse_guide_pdf.py` recognises elements by font size, colour and x-position (the
house style, `scripts/guide_style.py`). It works only on a PDF rendered **by this
skill with WeasyPrint and the bundled `guide.css`**. It is not for third-party guides,
and not for a PDF printed from a browser via the HTML fallback (fonts and positions
differ; presumed, untested). For any other PDF, rebuild in mode A and treat the old
PDF as one more source.

**Is it this skill's PDF?** Sector pages have a black square sector number, a
letter-spaced crag name above a large bold sector title, a shade bar starting with the
month, and numbered round route badges in two columns.

## Input → method → output

**Input:** the PDF; ideally the `*-sectors.csv` from the same build.
**Method:** walk the pages; classify spans by the F6 keys; group into lines per
column; attach spans to the current route badge; sort prose into fields; read the
contents table by header-derived x-bands; extract images per page; join the CSV.
**Output:** a `crag.json` draft plus a JSON report (per-sector counts, I2 mismatches,
review items).

```bash
python3 scripts/parse_guide_pdf.py --pdf old.pdf --out rebuilt/crag.json --geo-csv old-sectors.csv
```

## F6 — style keys (from `guide_style.py`)

| Element | Key |
|---|---|
| Route badge | white, 7.2 pt |
| Route name | bold 8.2 pt, ink #141414; a bold 8.2 pt span > 150 pt into the column is the grade |
| First ascent / bolts | #767676 |
| Note (hazard) | #9c3317 |
| Cross-reference | #3f6b3f |
| Stars | #c8442a digit + ★; unrated #bbbbbb "—"; rated zero "0★" in grey |
| Length | #555555 |
| Local name / † | 7 pt #4a4a4a / #9a9a9a |
| Route field note | #4b2a78 (bold "{by}, {date}:" prefix) |
| Top-pick symbol | #6a3fa0 |
| Sector title / number | bold 20 pt / white 15 pt |
| Prose heading / intro / box text | bold 9.4 pt / 8.8 pt / 7.8 pt |
| Columns | split at x = 300 pt; origins 40 / 308 |
| Contents bolt severity | text colour #c8442a = 3, #b26a10 = 2, #2f6b34 = 0, #8a8a8a = 1 |

Colours are matched with a small tolerance: the renderer rounds them (e.g. #141414
comes out as #131313).

## Known traps (already handled; keep them handled)

| Symptom | Cause | Fix in the parser |
|---|---|---|
| Badges attach to the wrong route (off by one) | Badges sit ~2 pt lower than names | Order badges 5 pt earlier |
| Stars or ★ read before the name | Fallback-font glyphs (★) sit higher | Line y = the leftmost span's y |
| Headline not found | Its row position varies | Find the 8 pt row containing "Shade" (its first bold span is the month) |
| Appendix text read as routes | Back pages after the last sector | Stop the route zone at an APPENDIX kicker or a 19 pt page title |
| Words glued or split | Line-end hyphens are real (no auto-hyphenation) | Join without a space after `[A-Za-z]-` |
| Letter-spaced headings ("W A R N I N G") | CSS letter-spacing | Compare with whitespace removed |
| Every image on every page | `page.get_images()` returns the shared list | `page.get_image_info(xrefs=True)` |
| Conditions paragraph duplicated after rebuild | Re-importing generated prose | Drop from "The wall faces…"/"By calculation…" through the paragraph containing "Calculated, not observed"; keep the rest as `conditions_extra` |
| Parser breaks after a style change | CSS drifted from the parser | Parser-relevant CSS is generated from `guide_style.py`; the round-trip test is required |

## After parsing

1. **Check I2:** per-sector parsed routes = the CSV's `routes_listed` (or `routes`).
   Report a mismatch; never paper over it.
2. Work through the report's `review` list: the crag name, an override's `table` and
   `short` cells (rebuilt from the headline), top-pick routes (their spine stars are
   not printed), editorial pages (not recovered — copy their text or rewrite them).
3. Without the CSV, rerun `crag_conditions.py` for the sun windows (and find or rebuild
   the axis file).
4. Continue in mode B (field notes) or mode A (new sources).
