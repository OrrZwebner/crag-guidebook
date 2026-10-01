# Aspect, sun window and shade hours

Read this before running `crag_conditions.py`, before writing any conditions text, and
whenever an observation disagrees with the calculation (P6).

## Input → method → output

**Input:** sector coordinates; a valley/road/river centreline (best) or none; the
conditions date and UTC offset; the horizon angle; any stated aspects.
**Method:** axis → bank → aspect (F3); solar track → sun window (F2); daylight minus
sun window → shade (F1).
**Output:** per sector `aspect`, `aspect_deg`, `bank`, `aspect_confidence`, `sun`;
`crag.conditions_meta` (sunrise, sunset, solar noon); printed as **shade**.

## F3 — aspect from the bank

A wall on the west bank of a valley faces east, and vice versa: aspect is the axis
normal pointing across the valley from the sector's bank. `aspect_manual` (degrees,
0 = north) overrides it and counts as high confidence.

- **Axis source.** `--axis file --axis-file axis.json` (a JSON list of `[lat, lon]`
  along the road or river) is best. `--axis osm --axis-bbox …` fetches OpenStreetMap
  (see `sources.md`). `--axis auto` fits a line through the sectors: measured against a
  real centreline it put about one sector in six on the wrong bank, which reverses its
  aspect and sun times, so every auto aspect is marked low confidence.
- **Three or fewer sectors** cannot define a line and a side: set `aspect_manual`.
- **Keep the axis file next to `crag.json`.** Without it the sun windows cannot be
  recomputed for a new edition.

## F2 — the sun window

A time sample t is lit iff

    elevation(t) > horizon   and   |((az(t) − aspect + 180) mod 360) − 180| < arc

with `arc` = 88° by default. W = [first lit sample, last lit sample], or none. The
horizon term matters: a wall in a gorge does not catch the sun at sunrise but when the
sun clears the far ridge. `--horizon`: ~25° deep narrow gorge, 10–15° broad valley,
0–5° open crag.

## F1 — shade is the complement

Daylight D = [sunrise, sunset] (from `conditions_meta`). Sun window W = [a, b] or none.

    S = D \ W = [sunrise, a) ∪ (b, sunset]        W = none → shade all day

Identity **I3**: |S| + |W| = |D| for every sector (`verify_guide.py` checks it).

Printing rule (`guide_style.shade_headline`): drop a shade segment shorter than 15 min;
the **longer** segment leads; the other follows as "also …".

Worked example (the synthetic fixture: sunrise 07:00, sunset 19:00, |D| = 720 min):

| Sector | W | Before a | After b | Headline |
|---|---|---|---|---|
| Lichen Slab | 09:00–13:00 | 120 min | 360 min | Shade (climbable) after 13:00 · also before 09:00 |
| Owl Buttress | 14:00–18:50 | 420 min | 10 min (dropped) | Shade (climbable) until 14:00 |
| Cold Corner | none | — | — | Shade all day |

Check: 120 + 240 + 360 = 720; 420 + 290 + 10 = 720.

Everywhere — headline, contents column ("Shade, June"), coordinate tables, planning
page, KML/GPX/CSV, prose — say **Shade**, never "Sun HH:MM–HH:MM". The CSV keeps the
raw calculated window in `calc_sun_from` / `calc_sun_to` plus a `shade` column.

## The accuracy caveat

Every calculated value is labelled calculated and approximate, and links to the
Important page, whose first item is always the caveat. Suggested wording:

> Shade times are calculated from each wall's aspect and the sun's position on
> <date>, with the far side of the valley taken as a <N>° horizon. They are
> approximate: overhangs, trees, side gullies and a wrongly placed bank all change
> them. Where someone has observed the wall, the observation is printed instead and
> marked.

## Cross-check

Find every source that describes conditions directly ("sunny until midday", "an
afternoon sector", "not climbable in summer") and compare. Report agreement and
disagreement on the How-to-read page in a "Cross-check" box — including a failure, if
there is one. Three independent agreements are what make the numbers credible; one
disagreement is how you catch a mislabelled aspect or a wrong bank.

## Observation overrides calculation (P6.6–8)

When a first-hand observation **contradicts** the calculation:

1. Set `shade_override` with `headline` (starts "Shade (observed <date>): …"),
   `sentence` (what the calculation said, "That is not what happens.", the observation
   in `<span class='mine'>`, what was *not* observed), `table` and `short` cells
   (both mention "observed" and "calc. said …").
2. The builder keeps the calculation visible under it, marked "contradicted", and
   flags the header aspect as "calc., contradicted".
3. Say what was not observed (e.g. "afternoon not observed").
4. Add a contradictions-appendix row.
5. Rerunning `crag_conditions.py` keeps the override.

When an observation **agrees**, keep the calculation and add the observation, credited,
to `conditions_extra` as corroboration.

A **crag-wide** observation ("one side of the valley is shaded until about X, because
the other side shades it") goes on the Important page and the planning page, credited
as first-hand.

## Planning page

`"generate": "shade_planning"` on a `mid_pages` entry groups sectors by their longer
shade segment: morning shade (sorted by how long the shade lasts), afternoon shade
(sorted by when it starts), shade all day, little shade. Sectors with an override sit
last in their group, with a note. Each row gets a pick: the top pick if there is one,
else the highest-starred route.
