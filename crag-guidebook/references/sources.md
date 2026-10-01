# Finding and reconciling crag sources

Read this before research (mode A, steps P1–P5) and before reconciling. Site-specific
facts are marked with the date they were observed; sites change, so re-check them.

## Contents

- [What each kind of source is good for](#what-each-kind-of-source-is-good-for)
- [The reconciliation key](#the-reconciliation-key)
- [Provenance discipline](#provenance-discipline)
- [Bolt condition](#bolt-condition)
- [Getting the data out](#getting-the-data-out)
- [Getting a valley centreline](#getting-a-valley-centreline)
- [Satellite imagery](#satellite-imagery)
- [Contradictions worth hunting for](#contradictions-worth-hunting-for)
- [Reading photographed route tables](#reading-photographed-route-tables)
- [Local-language names](#local-language-names)
- [Collecting topos: etiquette](#collecting-topos-etiquette)

---

## What each kind of source is good for

No single source has everything. They fail in predictable ways, so go in knowing
what you are collecting from each.

**theCrag** is almost always the spine. It has per-sector GPS, French grades,
community star ratings, logged-ascent counts (a real popularity signal), bolt
counts for a minority of routes, and — uniquely — explicit fixed-gear warnings
like *needs rebolting* or *bad bolting*. It is usually the only source with
coordinates precise enough to compute aspect from. What it lacks is history:
first-ascent dates and equipper names are patchy.

**The local club's printed guidebook** is the opposite. It carries first-ascent
dates, equipper names, original grades and the local star scale, and often the
only real topos. It is usually years out of date on new routes, and frequently
uses a different grading system and a completely different sector division. If
the person you are working for owns it, photographs of its pages are the single
highest-value input you can get — ask.

**The local club or regional website** (a regional climbing site, a federation site, a
regional wiki) typically reproduces the printed guide, sometimes with rope-length
advice the book omits. Treat it as a second copy of the book rather than an
independent source, and check whether it admits to being incomplete — they often
do, in a sentence people skip.

**Mountain Project, UKClimbing, 27crags** are thin outside their home countries,
but they carry approach descriptions that nobody else writes down — where to park,
what the path looks like, which retaining wall to aim for. Worth the visit for
that alone. They also rename and reorganise areas, which breaks old links and
creates duplicate pages; check edit histories if something looks odd.

**Blogs, forum threads, guiding-company pages, local news** fill in the texture:
bolting campaigns, festivals, access, which sectors guides actually take clients
to, tavernas. Local-language news is often the only record of who equipped what
and when.

**OpenStreetMap** gives you the road and river centreline, which is what turns
coordinates into aspect. See below.

---

## The reconciliation key

The hard part is not gathering; it is working out that source A's "Sector 2" and
source B's "Grey Tower" are the same rock.

**Start by looking for the naming convention.** Online databases are usually built
by locals transcribing the printed guide, and when the book numbers routes without
naming sectors, the person entering them names each sector after its best-known
route. So a route called *Salt Road* in the book becomes a sector called *Salt
Road* online. Once you spot one such pair, test it across the whole list — if
three or four hold, you have the key to the entire crag, and route-number ranges
map straight onto sector names.

**Then use first-ascent fingerprints.** A route with the same equipper and the
same year in two sources is the same route even when the name is transliterated
differently (one letter romanised two ways, different word endings). Date plus partner names
is a strong match; name similarity alone is not.

**Watch for splits and merges.** Databases often split a long route into "Route"
and "Route Extension" at different grades where the book lists one long pitch.
Neither is wrong. Print both and say which is which, because a climber arriving
with a 60 m rope needs to know the book's 50 m version exists.

**Geography is the tiebreak.** Sort every sector by coordinate along the valley
axis. If the resulting order matches the book's route numbering, your mapping is
almost certainly right. If one sector lands out of sequence, that is the one to
re-examine.

**Verify by counting.** When your assembled route list totals exactly what the
spine source claims for the crag, you have not silently dropped or duplicated a
sector. This catches real mistakes and takes a second.

---

## Provenance discipline

The value of a compiled guide is that the reader can tell where each fact came
from and how much to trust it. That means:

- **Lead with one source and name it.** Pick the spine (usually theCrag for
  grades and stars) and be consistent, so a reader knows what an unqualified
  number means.
- **Print the disagreement, don't average it.** If the book says VII and the
  database says 6b+, show both. Averaging invents a number nobody measured.
- **Say when something is nobody's claim.** Anything you calculated — aspect, sun
  times, estimated quickdraw counts — must be labelled as calculated, with the
  method available. A reader who cannot tell your arithmetic from a local's
  observation cannot judge either.
- **Absence is not evidence.** "No source mentions the bolts" is not "the bolts
  are fine", and a guide that renders those the same way is dangerous. Use a
  distinct grey/neutral state for *unknown* and say explicitly what it means.
- **Keep a contradictions list.** Every conflict you could not resolve goes in an
  appendix with both readings and what you did about it. This is often the most
  useful page in the book, and it is what makes the guide honest rather than
  merely confident.

---

## Bolt condition

This is the section that can hurt somebody, so it gets its own discipline.

Collect, per route and per sector: explicit warnings from any source, the year of
equipping, any record of rebolting, and the bolt material if anyone states it
(rarely). Then classify each sector into four states and colour them consistently:

| State | Meaning |
|---|---|
| **Flagged** | A source explicitly says rebolting is needed, or bolting is bad |
| **Caution** | Run-outs, loose rock, or some routes flagged but not all |
| **Maintained** | New hardware, or documented rebolting |
| **Unknown** | Nobody has said anything |

Two things make this useful rather than decorative. First, give the count, not
just the state: *"six of thirteen need rebolting"* tells a climber which half of
the wall to avoid. Second, write down somewhere prominent that Unknown is not a
clean bill of health — most crags were equipped decades ago and simply never
reported on.

Note the interaction with popularity: a sector with excellent routes and zero
logged ascents is usually telling you something, and it is often the bolts.

---

## Getting the data out

Database sites frequently block automated fetchers while serving browsers fine,
and they rate-limit aggressively.

- Try the normal fetch tool first.
- If a plain fetch gets a 403, use a real browser if one is available, reading pages
  as text rather than screenshots. If the browser is blocked too (403/429, "Forbidden",
  a challenge page), stop using that site for this guide and record the gap — never
  work around bot protection.
- **Pace it.** Roughly ten seconds between page loads avoids the throttle that a
  burst will trigger. Getting throttled costs far more time than pacing does.
- Fan out across sources in parallel, but keep each agent to one source so one
  site's rate limit does not stall the rest.
- Ask any research agent to report *what it could not get*, explicitly. A gap you
  know about is recoverable; a gap you don't is a hole in the book.

Coordinates are often not in the visible text but are in the page markup. A
regular expression for a latitude/longitude pair over the raw HTML usually finds
them when reading the rendered text does not.

---

## Getting a valley centreline

`crag_conditions.py --axis auto` fits a line through the sectors and works, but
measured against a real centreline on a winding gorge it put about one sector in
six on the wrong bank — which reverses its aspect and therefore its sun times.
Get real data if you can.

OpenStreetMap serves it from:

```
https://www.openstreetmap.org/api/0.6/map?bbox=<minlon>,<minlat>,<maxlon>,<maxlat>
```

Try `--axis osm` first. If egress policy blocks it, open that URL in a browser
that has access and extract the way you want — a `highway` way whose `name`
matches the valley road, or a `waterway`. Keep the node coordinates, sort them
along the valley, thin them to roughly one point every 30–40 m, and save as a JSON
list of `[lat, lon]` for `--axis-file`.

A river often traces the valley better than the road, which may climb one flank.
If both exist, prefer whichever runs closer to the sectors.

---

## Satellite imagery

Expect to be unable to produce a satellite image file. Tile servers are commonly
blocked, and a screenshot taken in a browser arrives as pixels in a conversation
rather than as a file you can place in a PDF.

This is why `export_geo.py` writes KML. Imported into Google My Maps or opened in
Google Earth it gives the reader exactly what they wanted — every sector pinned
and labelled on satellite imagery, with the details in the info box, working on a
phone. It is better than a static image, because it zooms and travels.

Say so plainly rather than apologising: the printed maps carry the scaled geometry
and the KML carries the imagery.

The printed maps are not bare pins: `make_maps.py` draws OpenStreetMap vector data
(Overpass API) under them — roads by class, tracks, footpaths, cliffs with their
down-slope ticks, water, buildings and car parks — and caches it next to the map.
Overpass rate-limits bursts (429 after ~3 quick queries, observed 2026-10-01); the
script paces requests, falls through to public mirrors on 5xx, and stops on 403/429.

---

## Contradictions worth hunting for

From experience, these recur across crags and are worth checking deliberately:

- **Sector count and route count** disagree wildly between sources. Usually one is
  simply older.
- **A route in two sectors.** Common where databases have reorganised.
- **Grades drifting** between the printed book and the database, particularly at
  the easy end and on unrepeated hard routes. Question marks in a printed guide
  mean *proposed*, and often stay proposed for decades.
- **Aspect stated one way and conditions described another** — "south-east facing"
  next to "shaded all morning". One of them is wrong; the calculation usually
  tells you which.
- **Impossible altitudes** — a sector further up the valley listed as lower than
  one below it.
- **Ascent counts differing** between a site's own parent and child pages.
- **Distances and approach times** varying by a factor of two between tourist
  sources. Prefer the local club's figure.

---

## Reading photographed route tables

Read every page image before writing anything. From each route table take the
local-script name, the original grade (often UIAA), the first ascent, the local star
scale and any warnings.

- **Reproduce names exactly as printed.** Unaccented capitals stay unaccented capitals;
  do not "correct" spelling or add accents.
- **Attach by route number, never by name similarity.** Store the printed guide's
  number in the route's `xref` (e.g. `"Book #12 · VIII · ★★"`) and use it as the join
  key. Similar names across sources are a hint, not a match.
- Crop the topos out of the page photos; auto-contrast helps against lamp glare.
  Credit the book in the caption and say the compilation is for personal use.
- HEIC photos: convert with `scripts/photo_gps.py --to-jpg DIR` (needs Pillow +
  pillow-heif) or the platform's own converter (e.g. `sips` on macOS).

## Local-language names

Each route and sector can carry `local_name` with `local_src`:

| `local_src` | Meaning | Rendered |
|---|---|---|
| `source` | Printed guide, a sign at the crag, or a database | as is |
| `reconstructed` | No source has it; back-transliterated from a Latin name that is clearly a local-language word | with a grey † |
| (blank) | Spelling uncertain, or the name is not local-language in origin | nothing |

- **Check a database before relying on it for local names.** Some databases store
  only Latin names (observed 2026-09 on one large database: no local-script names at
  all). Look at one area page and one route page first.
- Leave a name blank rather than guess; a wrong name is worse than none. List blanks
  in `HANDOVER.md`, and add an item: check † names against the rock on the next visit.
- Explain † on the "How to read" page, and report the tally sourced / reconstructed /
  blank (identity I4; `verify_guide.py` checks it).

## Collecting topos: etiquette

The source ladder (OpenStreetMap + Commons first, then official APIs with the user's own
key, then the user's own images) and the provenance fields are in `references/topos.md`.

- Use only topos that are **freely viewable**. Where a full-size or high-resolution
  view sits behind a paid tier, save the freely displayed image at the size it is
  displayed, never the paid version. (Observed 2026-09 on one large database: full-size
  photo-topos were a paid feature; the free view was smaller.)
- **Never bypass** a paywall, a login, bot protection or a CDN block, and do not
  fetch around a browser to get an image the site serves only to browsers.
- **Pace page loads** (about 10 s apart). If a site starts refusing — "Forbidden",
  challenge pages — **stop**. Record which sectors still lack topos, tell the user,
  and let them decide. (Observed 2026-09: a block after roughly seven rapid loads.)
- Credit every topo in its caption: the source, "community-contributed" where that
  applies, and whether its route numbers match the table.
- Keep the spine database's route numbering when you use its topos, so the numbers on
  the topo match the table.
- Save files by convention — `topo/<src>_<NN>[a|b|c].<ext>` (topos) and
  `img/<src>_<NN>[a|b|c].<ext>` (photos), NN = sector number — and run
  `scripts/attach_images.py --crag crag.json --credit "<src>=<caption>"`. A topo found
  later is dropped into `topo/` with the right name and appears on the next rebuild.
