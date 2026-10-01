Load when adding topos or sector photos (mode A step P5, mode B photos).

# Topos and sector photos: the source ladder

Work down the ladder in order and stop at the first rung that gives you what you need
for a sector. Every image, from any rung, gets the same provenance fields and a credit.

## Contents

- [Route data from a connected MCP tool](#route-data-from-a-connected-mcp-tool)
- [Rung 1 — OpenStreetMap + Wikimedia Commons](#rung-1--openstreetmap--wikimedia-commons)
- [Rung 2 — official APIs, with the user's own key](#rung-2--official-apis-with-the-users-own-key)
- [Rung 3 — images the user supplies](#rung-3--images-the-user-supplies)
- [Provenance fields](#provenance-fields)
- [Rules](#rules)
- [The route-line format](#the-route-line-format)

---

## Route data from a connected MCP tool

If the AI app you are running in has a climbing MCP tool connected — for example an
OpenBeta server such as https://github.com/jacKlinc/openbeta-mcp, which finds crags and
routes through OpenBeta's public API — use it **first for route data** (names, grades,
coordinates) and treat it as one more source to reconcile. It gives route data only,
not topos. Never assume such a tool exists: check what tools you actually have, and if
there is none, carry on without it. A skill cannot install or connect one.

## Rung 1 — OpenStreetMap + Wikimedia Commons

The only open, scriptable topo source. OpenClimbing (https://openclimbing.org, code at
https://github.com/jvaclavik/openclimbing, built on https://github.com/zbycz/osmapp)
stores climbing data in OpenStreetMap and photos on Wikimedia Commons:

- crags and areas are OSM objects tagged `climbing=crag` / `climbing=area`
  (tagging: https://wiki.openstreetmap.org/wiki/Climbing);
- a photo is linked with `wikimedia_commons=File:…`, further photos with
  `wikimedia_commons:2=File:…`, `wikimedia_commons:3=…`;
- a route (`climbing=route_bottom` node or `climbing=route` way) carries the same
  `wikimedia_commons[:N]` tag naming the photo it is drawn on, and its line on that photo
  in `wikimedia_commons[:N]:path` (format below).

```bash
python3 scripts/fetch_topos.py find  --lat <lat> --lon <lon> --radius 1500 > osm.json
python3 scripts/fetch_topos.py fetch --objects osm.json --crag crag.json [--select node/1,way/2] [--sector N]
```

`find` asks the Overpass API for every climbing-tagged object in the radius (or
`--bbox`) and lists name, coordinates, OSM id, image tags and path tags. `fetch` asks
the Commons API for each chosen photo's licence, author and page, downloads a thumbnail
to `topo/osm_<NN><a-z>.<ext>`, attaches it to the nearest sector (or `--sector N`), and
stores the route lines drawn on that photo. NC or unknown licences are skipped unless
the user has confirmed personal use (`--allow-personal-use`). OSM data is © OpenStreetMap
contributors (ODbL): say so on the credits page.

## Rung 2 — official APIs, with the user's own key

Only with the user's own key and their approval; never with a key you found.

- **theCrag**: the API is not open to non-commercial apps; access needs a signed
  agreement (https://www.thecrag.com/en/article/api — the page refused an automated
  fetch on 2026-10-01; read it in a browser).
- **Mountain Project**: its data API was deprecated in 2020.
- **UKClimbing / Rockfax, 27crags**: no public API.

So for most users this rung is empty. Viewing these sites in a browser, at the free
size, is still allowed under the etiquette in `references/sources.md`.

## Rung 3 — images the user supplies

Photos of a printed guidebook, screenshots, their own photos, or URLs to images they
have the right to use. Save by the naming convention and attach:

```bash
python3 scripts/attach_images.py --crag crag.json \
    --credit "book=Topo — from the printed guidebook (personal use)" \
    --author "book=<guidebook title>" --licence "book=personal use"
```

## Provenance fields

Every entry in a sector's `topos[]` records:

| Field | Example |
|---|---|
| `image` | `topo/osm_03a.jpg` |
| `caption` | `Topo — <title> · <Artist> · <licence> · Wikimedia Commons` |
| `source` | `Wikimedia Commons via OpenStreetMap (node/123)`, `book`, `user` |
| `licence` | `CC BY-SA 4.0`, `personal use`, `own photo` |
| `credit` | the author as the source states it |
| `source_url` | the Commons file page, or the URL the user gave |
| `retrieved` | `2026-10-01` |

Optional: `lines` (route lines, below) and `size` `[w, h]` of the downloaded image.
`build_guide.py` adds credit and licence to the caption if missing and lists every
credit on the credits/sources page; `verify_guide.py` fails a topo without `credit` or
`licence` and warns on `personal use` / `own photo`.

## Rules

- Never get around a login, paywall, bot protection or CDN block, and never scrape
  against a site's terms.
- Stop at the first 403, 429 or challenge page. `fetch_topos.py` does this itself and
  prints `{"status": "blocked"}` (or `"offline"`). Record the gap — which sectors still
  lack topos, and where it stopped — in `HANDOVER.md` and tell the user.
- NC (non-commercial) or unknown-licence images: personal use only, and only after the
  user confirms. Mark the licence as it is, and say "personal use" in the caption.
- Credit everything: on the caption and on the credits page.

## The route-line format

`wikimedia_commons[:N]:path` holds points `x,y` separated by `|`. `x` and `y` are
fractions (0–1) of the image width and height, measured from the top-left corner. A
point may end in one letter: `B` bolt, `A` anchor, `P` piton, `S` sling, `U`
unfinished. A `:` before the `|` makes the segment to the next point dotted.
Example: `0.68,0.82|0.64,0.45B:|0.55,0.17A`.
Sources: https://wiki.openstreetmap.org/wiki/Key:wikimedia_commons:path and the parser
`src/components/FeaturePanel/Climbing/utils/pathUtils.ts` and `boltCodes.ts` in
https://github.com/zbycz/osmapp (commit 2f03e4f, read 2026-10-01).
`fetch_topos.py` stores each line raw and parsed; `build_guide.py` draws it over the
photo (dotted segments dashed, bolts as dots, anchors as rings).
