# HANDOVER.md and the decisions log

Read this at the end of every build (P10). A guide without its source forces a mode-C
reconstruction later, so the handover is part of the deliverable.

## Always save next to the guide

`crag.json`, the axis file, `img/`, `topo/`, `maps/`, the geo files, `HANDOVER.md`,
`notes/decisions.md`.

## HANDOVER.md template

```markdown
# <Crag> guide — handover (<date>)

## State
- Output: <file> (<pages> pages, renderer: weasyprint | html), edition <n>
- Checks: verify_guide.py <passed>/<total>; pages looked at: <list>
- Files: crag.json, <axis file>, img/, topo/, maps/, <slug>-sectors.{kml,gpx,csv}

## Where the data came from
| Data | Source | Count |
|---|---|---|
| Routes, grades, stars | <spine> | <n> routes |
| Local names | sourced <a> / reconstructed † <b> / blank <c> | = <n> |
| Topos | <sources> | <k> sectors of <m> |
| Shade | calculated (<axis>, horizon <h>°, <date>); observed overrides: <sectors> |
| Field notes | <by>, <date> | sectors <list> |

## Open gaps
1. Sectors still without a topo: <list> (drop files in topo/ as <src>_<NN>.<ext>, run
   attach_images.py, rebuild)
2. Blank local names: <list>
3. † names to check against the rock on the next visit: <list>
4. Conditions not observed: <e.g. afternoon at sector X>
5. Numbering choices: <which source's numbering, and why>
6. Privacy in photos: <plates/faces to blur, or "none seen">

## Rebuild
    python3 <skill>/scripts/crag_conditions.py --crag crag.json --axis file --axis-file <axis>
    python3 <skill>/scripts/make_maps.py --crag crag.json --out maps/ --axis-file <axis>
    python3 <skill>/scripts/export_geo.py --crag crag.json --out . --slug <slug>
    python3 <skill>/scripts/build_guide.py --crag crag.json --out <name>_v<n>.pdf
    python3 <skill>/scripts/verify_guide.py --guide <name>_v<n>.pdf --crag crag.json
```

## notes/decisions.md

Log each decision the user makes, with its date: what was decided, why, what it
touches.

```markdown
## <YYYY-MM-DD> — <short title>
- **Decided:** <e.g. observation wins at sector X; calculation kept visible>
- **Why:** <e.g. first-hand observation on <date> contradicts the calculated aspect>
- **Touches:** <crag.json sector X shade_override; appendix row; planning page>
```
