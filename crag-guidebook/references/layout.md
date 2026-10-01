# The crag file, the page order, and rendering

Read this before filling `crag.json` (every mode), before writing the editorial pages,
and whenever a rendering problem appears. `examples/crag.json` is a complete, synthetic
file that exercises every field below.

## Contents

- [crag.json schema](#cragjson-schema)
- [Page order](#page-order)
- [What to write on each editorial page](#what-to-write-on-each-editorial-page)
- [Renderer: PDF or the HTML fallback](#renderer-pdf-or-the-html-fallback)
- [WeasyPrint gotchas](#weasyprint-gotchas)
- [Verifying the built guide](#verifying-the-built-guide)

---

## crag.json schema

One file holds everything. `crag_conditions.py` writes the aspect and sun fields into
it; `make_maps.py`, `export_geo.py`, `build_guide.py` and `verify_guide.py` read it;
`attach_images.py` adds to `topos`; `parse_guide_pdf.py` (mode C) rebuilds a draft of it.
Keep it, the axis file and the image folders next to the guide.

```jsonc
{
  "crag": {
    "name": "Hollowmere Gorge",
    "subtitle": "…",
    "country": "…",                    // shown on the cover tag
    "year": 2026,
    "month_label": "June",             // shade bar and "Shade, June" contents column
    "tz_offset": 0,                    // UTC offset on the conditions date
    "conditions_date": "2026-06-15",
    "horizon_deg": 15,                 // how high the far valley wall stands
    "spine_total": 12,                 // routes the spine source claims (identity I1)
    "field_notes_by": "A. Visitor",    // mode B: name or role, as they want credit
    "field_notes_date": "2026-06-01",
    "top_pick_symbol": "♪",            // default ♪
    "top_pick_label": "Visitor's top pick",
    "approach_tips": ["…", "…"],       // crag-wide tips → the Approaches box
    "conditions_meta": {…}             // written by crag_conditions.py (sunrise, sunset…)
  },

  "contents_title": "The four sectors at a glance",
  "cover": {"image": "img/cover.jpg", "tag": "…", "title_html": "Mini guide:<br>…",
            "blurb": "Sources, edition date, what it contains."},

  "front_pages": [                     // between contents and maps; FIRST = Important
    {"kicker": "Read this first", "title": "Important before you go",
     "html": "<div class='imp'><div class='boxh'>Read this first</div><ol><li>…</li></ol></div>"},
    {"kicker": "The crag", "title": "…", "approaches": true, "html": "…"}
  ],                                   // "approaches": true → Approaches box appended here
  "maps": [{"kicker": "Overview · sectors 1–4", "title": "…", "image": "maps/map.png",
            "caption": "…", "sectors": [1, 2, 3, 4], "html": "<p>…</p>"}],
  "mid_pages": [                       // after maps, before sectors
    {"kicker": "Planning", "title": "Where the shade is", "generate": "shade_planning",
     "html": "<div class='box'>If you have one day…</div>"}
  ],                                   // "generate": "shade_planning" → tables built from data
  "back_pages": [{"kicker": "Appendix", "title": "Contradictions between the sources",
                  "html": "<table class='tbl'>…</table>"}],
  "waypoints": [{"name": "Village (food, water)", "lat": 0.0, "lon": 0.0}],

  "sectors": [
    {
      "n": 1, "name": "Lichen Slab",
      "local_name": "…",                          // sector local name (optional)
      "en": "Lichen slab",                        // English gloss (optional)
      "lat": -30.0, "lon": -20.001,
      "parking": [-29.9995, -20.002],             // adds a KML/GPX pin; printed in facts
      "asl": "40 m",
      "routes_count": 4,               // the source's own count — cross-check
      "ticks": 120,                    // logged ascents = popularity
      "grades": "5a–6b", "height": "20 m", "qd": "8",
      "bolted": "2001", "bolt_status": "…",
      "bolt_severity": 2,              // 0 maintained, 1 unknown, 2 caution, 3 flagged
      "intro": "…", "climbing": "…", "gear": "…", "warn": "…",
      "approach": "…", "walk": "2 min", "busy": "…",
      "conditions_extra": "",          // a credited observation that AGREES, a source quote
      "aspect_manual": null,           // degrees; overrides the calculated aspect
      "shade_override": {              // an observation that CONTRADICTS the calculation
        "headline": "Shade (observed 2026-06-01): until about 10:00 · afternoon not observed",
        "sentence": "By calculation … <b>That is not what happens.</b> <span class='mine'>…</span>",
        "table": "<b>until ~10:00</b><div class='tgr'>observed 2026-06-01 · calc. said 13:00</div>",
        "short": "until ~10:00<br><span class='small'>observed 2026-06-01</span>"
      },
      "field_notes": ["Paragraph (HTML allowed).", "…"],
      "topos": [{"image": "topo/book_01.png", "caption": "Topo — … (personal use)",
                 "source": "book", "credit": "…", "licence": "personal use",
                 "source_url": "", "retrieved": "2026-06-01"},
                {"image": "img/photo_01a.jpg", "photo": true, "caption": "… — photo A. Visitor, 2026-06-01",
                 "source": "user", "credit": "A. Visitor", "licence": "own photo", "retrieved": "2026-06-01"},
                {"image": "topo/osm_01a.jpg", "caption": "Topo — … · Wikimedia Commons",
                 "source": "Wikimedia Commons via OpenStreetMap (node/…)", "credit": "…",
                 "licence": "CC BY-SA 4.0", "source_url": "https://commons.wikimedia.org/wiki/File:…",
                 "retrieved": "…", "size": [1280, 960],
                 "lines": [{"name": "…", "grade": "6a", "path": "0.2,0.9|0.3,0.1A",
                            "points": [{"x": 0.2, "y": 0.9}, {"x": 0.3, "y": 0.1, "type": "anchor"}]}]}],
      "routes": [
        {"n": 1, "name": "Green Mile", "grade": "5a", "stars": 1, "length": "15 m",
         "bolts": null, "type": "sport",
         "fa": "I. Nvented, 2001",
         "note": "",                   // hazards: red, tints the row (keywords below)
         "xref": "Book #12 · VIII · ★★", // the other source's reading, green
         "local_name": "…", "local_src": "source",   // or "reconstructed" (†) or omit
         "rating": "top_pick",         // replaces the star cell with the symbol
         "field_note": "…"}            // rendered "{by}, {date}: …"
      ]
    }
  ]
}
```

Fields written by `crag_conditions.py`: `aspect`, `aspect_deg`, `bank`,
`dist_to_axis_m`, `axis_bearing`, `sun`, `sun_flat`, `aspect_confidence`, and
`crag.conditions_meta`. It never touches `shade_override`, `conditions_extra` or prose.

- `stars: null` = unrated, `0` = rated zero. They render differently; never use `0`
  for "no rating".
- A `note` containing REBOLT, BAD BOLTING, RUN-OUT, RUNOUT, LOOSE ROCK, BIRD NEST or
  DANGER tints the row. Phrase hazard notes with the keyword in them.
- `local_src` also accepts `translit` (= reconstructed) and `book`/`guidebook`
  (= source); `rating` also accepts `note` (= top_pick).
- A legacy single `topo` + `topo_caption` still works and is shown first.
- Topo provenance (`source`, `credit`, `licence`, `source_url`, `retrieved`) is
  required by `verify_guide.py`; `build_guide.py` appends credit and licence to a caption
  that lacks them, draws `lines` over the image, and lists every credit in a "Topo and
  photo credits" box on the page marked `"credits": true` (else the first front/back page
  titled with "credits" or "sources"). See `references/topos.md`.
- Prose fields are escaped (plain text). `field_notes`, `shade_override.sentence` and
  all `html` fields are raw HTML.

---

## Page order

`build_guide.py` emits, in this order:

1. **Cover** — full-bleed image, title, year, blurb (sources and edition date).
2. **Contents** — landscape; live page numbers in the PDF; columns include **Shade**.
3. **`front_pages`** — Important before you go (first), About / sources and method,
   How to read, the crag page (with the Approaches box), bolts / practicalities.
4. **Map pages** — each with a coordinate table (parking included).
5. **`mid_pages`** — shade-based planning, where to go for what.
6. **Sector pages** — header (number, name, local name · gloss, shade headline),
   facts, prose, field-notes box, route rows, topos and photos.
7. **`back_pages`** — the contradictions appendix.
8. **Index** — every route A–Z.

Skip the generated pages with `--no-contents` / `--no-index`.

---

## What to write on each editorial page

Suggested shape, not a template.

**Important before you go** (first front page, `div.imp` numbered list): the
shade-accuracy caveat (always); crag-wide hazards (rockfall → helmet); anchor type;
approach advice; any crag-wide conditions observation. In a revised edition add a
"symbols new in this edition" box and a field-notes provenance box.

**About / sources and method.** What each source gave, where they disagreed and how
that was resolved; name the spine; list sources; "what this guide is not"; credits
and use terms (topos are someone's copyright: personal use).

**How to read.** Grades and the conversion table, stars and the top-pick symbol,
local names and †, warnings and field notes (the purple colour), shade and its method,
the cross-check against sources (including any failure), the sun geometry on the
conditions date.

**Crag page.** History, getting there, parking, food, water, season, children, an
at-a-glance box, the bolt-condition summary box, and — automatically, from
`crag.approach_tips` — the Approaches box.

**Planning** (`mid_pages`). Use `"generate": "shade_planning"`: sectors grouped into
morning shade / afternoon shade / shade all day / little shade, observed overrides
last with a note, and a "pick" per sector (a top pick, else the highest-starred). Add
the "if you have one day" paragraph and a "where to go for what" page yourself.

**Contradictions appendix** (`back_pages`). Subject, the disagreement, what this guide
did. Include resolved and unresolved ones, and every observation-vs-calculation conflict.

Use `<div class='two'>` for two columns, `<div class='box'>` + `<div class='boxh'>` for
boxes, `<span class='mine'>` for first-hand text, `<table class='tbl'>` for tables.

---

## Renderer: PDF or the HTML fallback

`build_guide.py` tries WeasyPrint. If the import or the render fails — `ImportError`,
or `OSError` when system libraries such as pango are missing — or `--force-html` is
given, it writes **one self-contained HTML file** instead: CSS inlined, every image
embedded as a base64 `data:` URI, UTF-8, no external references. Its stdout JSON says
`"renderer": "html"` and carries the print steps. Give the user these steps:

1. Open the `.html` file in a browser (Chrome, Edge, Firefox or Safari).
2. Choose **Print**.
3. Set the destination to **Save as PDF**, paper **A4**, and turn **Background
   graphics** on. Save.

Differences from the WeasyPrint PDF: browsers cannot compute `target-counter()`, so
the contents shows sector numbers (§1, §2…) instead of page numbers; page-number
footers and landscape pages depend on the browser's `@page` support (as of 2026,
check the MDN compatibility tables). Sector pages still start on a new page, and
backgrounds print when Background graphics is on. A PDF printed from the browser is
not parseable by mode C.

Installing WeasyPrint (`pip install weasyprint`, plus pango on some systems) is the
user's call: ask before installing anything.

---

## WeasyPrint gotchas

The bundled `guide.css` already handles these; this is so you do not undo them.

- **Flexbox does not fragment across pages.** A tall flex row silently spills, leaving
  half-blank pages. Use `column-count` for anything that can overflow.
- **`break-inside` is ignored on flex rows.** Each route row is wrapped in a block
  `div.rtw { display:block; break-inside:avoid }`, otherwise rows split across columns.
- **Side-by-side blocks that must stay together** (a map beside its caption) use a
  plain `<table>`.
- **Live page numbers** come from `target-counter(attr(href), page)` on an `<a>` in the
  contents table.
- **Named pages for landscape:** `@page landscape { size: A4 landscape }` + `page: landscape`.
- **Missing images fail silently**, so `build_guide.py` checks every referenced file
  first and refuses to build (JSON lists what is missing).
- **Fonts.** Bitstream Charter, then DejaVu Serif (covers Greek, Cyrillic and most
  diacritics). Check local-script names render rather than showing boxes.
- **Parser keys.** The CSS for every element mode C recognises is generated from
  `scripts/guide_style.py` and appended after `guide.css`. Change sizes and colours
  there, not in the CSS, or the round trip breaks.

---

## Verifying the built guide

Run `scripts/verify_guide.py --guide <pdf|html> --crag crag.json [--baseline old.json]`;
it checks the identities and wording listed in its `--help`. Then **look**: render or
open the cover, contents, Important page, a dense sector, a sparse sector, every sector
with field notes or an override, and the index. Pagination faults are obvious to the
eye and invisible to a script. Also check that derived numbers (draws, rope) match the
prose.
