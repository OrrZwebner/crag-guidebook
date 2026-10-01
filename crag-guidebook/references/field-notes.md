# Mode B — revising a guide with a visitor's field notes

Read this when someone hands over their own notes, photos or opinions from a visit and
wants them in the guide (procedure PB).

## Input → method → output

**Input:** an existing `crag.json` from this skill (if there is only a PDF this skill
made, run mode C first — `rebuild-from-pdf.md`); free-text notes; photos; the visit
date; how the visitor wants to be credited (a name or a role).
**Method:** split the notes into atomic statements and route each to one place.
**Output:** a new edition (`<name>_v2.pdf`, the previous edition kept) with field-notes
boxes, per-route notes, observed-shade overrides, an updated Important page, the
Approaches box, photos, updated geo files and `HANDOVER.md`.

## 1. Attribution

Set `crag.field_notes_by` and `crag.field_notes_date`. The builder prints
"Field notes — {by}, visit of {date}" on sector boxes and "{by}, {date}: …" on route
notes. One visitor per edition (multiple visitors: ask how to credit them).

## 2. Route each statement

| Statement is about… | Goes to | Notes |
|---|---|---|
| The whole crag: hazards, anchors, general approach advice, crag-wide shade | Important page (`div.imp` item, `<span class='mine'>`) and/or `crag.approach_tips` | Crag-wide shade also goes on the planning page |
| A sector: parking, approach, rock, bolts, shade, the base, a grade feel | `sector.field_notes[]` (one paragraph each) | Also adjust the sector prose where it is now wrong — e.g. append "do not scramble straight up — see the field notes" to `approach` |
| A route | `route.field_note` | The visitor's grade or star opinion goes **in the note**; it never overwrites the spine grade or stars |
| A personal favourite | `route.rating: "top_pick"` | The symbol replaces the stars on that route only; quote the spine stars in the field note; excluded from the star mean |
| Sun or shade | `conditions.md` → override (contradicts) or `conditions_extra` (agrees) | Say what was not observed |
| Parking | `sector.parking` `[lat, lon]` + prose | From a parking photo's EXIF: `scripts/photo_gps.py photo.jpg`; adds a KML/GPX pin |
| Photos | `sector.topos[]` with `"photo": true`, caption "… — photo {by}, {date}" | Name them `img/<src>_<NN>[a-c].jpg` and run `attach_images.py`; the cover image if the user names one |
| Bolts ("new bolts", "spinner") | `field_notes` | Do not change `bolt_severity` automatically; ask |

## 3. Identify each route the visitor names

Match by sector and route number, or by the name in the table. Flag fuzzy matches —
spelling differences, numbering off by one — to the user **before** writing them.

## 4. Photos and privacy

Before sharing, look at every photo for licence plates and faces; strip or blur as the
user decides. EXIF carries the exact position and time — mention it. List anything
unresolved in `HANDOVER.md`.

## 5. Edition

- Write the output as a new edition (`<name>_v2.pdf` / `.html`); keep the previous one.
- Update the cover blurb (sources, "field notes from a visit on <date>", "Revised
  edition, <date>") and the Important page (a "symbols new in this edition" box and a
  field-notes provenance box explaining the purple colour).
- Run P6 (conditions), then build, verify and hand over (`handover.md`).
