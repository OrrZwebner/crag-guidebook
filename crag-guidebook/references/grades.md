# Grades, stars and quickdraws

Read when converting grades, choosing a star scale, or deriving quickdraw and rope
numbers for the gear prose and the contents table. Conversion tables are conventional
and approximate, not a formal standard.

## Grade systems

Pick one system for the whole book and convert everything into it. French sport
grades are the usual choice for a sport crag, because that is what databases and
most climbers travelling to one already use. Keep the original grade visible
alongside it wherever a source disagrees — the conversion is lossy and the reader
deserves to see what was actually written.

### UIAA ↔ French

| UIAA | French | UIAA | French |
|---|---|---|---|
| IV | 4a | VIII− | 6c+ |
| V | 4c / 5a | VIII | 7a |
| V+ | 5b | VIII+ | 7a+ |
| VI− | 5c | IX− | 7b |
| VI | 6a | IX | 7b+ / 7c |
| VI+ | 6a+ | IX+ | 7c+ / 8a |
| VII− | 6b | X− | 8a+ |
| VII | 6b+ | X | 8b |
| VII+ | 6c | X+ | 8b+ |

### YDS ↔ French (rough)

| YDS | French | YDS | French |
|---|---|---|---|
| 5.7 | 5a | 5.11c | 6c+ |
| 5.8 | 5b | 5.11d | 7a |
| 5.9 | 5c | 5.12a | 7a+ |
| 5.10a | 6a | 5.12b | 7b |
| 5.10b | 6a+ | 5.12c | 7b+ |
| 5.10c | 6b | 5.12d | 7c |
| 5.10d | 6b+ | 5.13a | 7c+ |
| 5.11a | 6c | 5.13b | 8a |

## Conversion pitfalls

**Consensus drifts, and the table does not.** A route first graded VI− in 1995 may
sit at 6a+ on a database today after a hundred ascents. That is not a conversion
error, it is thirty years of opinion. Where the two disagree, print both rather
than picking — and if the gap is more than one grade, say so in the route note,
because it usually means the route is polished, broken, or was always soft.

**Question marks mean proposed.** Printed guides mark unrepeated grades with `?`.
Databases usually drop the mark, which silently promotes a guess to a fact. Carry
the mark through, especially on hard routes with no logged ascents — those grades
have never been tested by anyone.

**Split routes carry split grades.** Where a database has "Route 6a+" and "Route
Extension 7c" but the book has one 50 m line at IX, the book's grade describes the
extension. Line them up before converting or you will publish a 6a+ that is
actually 7c.

**Mixed systems within one source.** Some sites carry both UIAA and French in the
same crag, depending on who entered each route. Check for grade shapes rather than
assuming: `VII+` and `6c` in the same list means someone switched systems, not
that there are two routes.

**Aid grades ride along.** `VII+ A1` converts the free part only; keep the `A1`.

## Stars

Star scales differ: community databases usually run 0–3, printed guides often 0–4
or 0–5. Convert nothing. Pick the scale your spine source uses, state it once, and
show the other source's rating separately where it exists.

Two things worth surfacing in a contents table:

- **the mean across rated routes** — a quick sense of sector quality, and
- **the count of top-rated routes** — which matters more. A sector averaging 2.2
  with six three-star lines is a better day than one averaging 2.4 with none.

Say explicitly that stars measure quality, not safety. Some of the best-starred
routes at a neglected crag are the ones nobody has touched for a decade, and the
star rating says nothing about the bolts.

## Top pick

A visitor's personal top pick (`rating: "top_pick"`) replaces the star cell on that
route only, with a distinct symbol (default ♪, `crag.top_pick_symbol`). The spine
stars stay in the data, are quoted in the route's field note, and the route is left
out of the sector's star mean: stars are a community scale, the pick is personal.

## Quickdraw counts

Readers want one number per sector: the most draws any single route needs.

Derive it, in order of preference:

1. **Published bolt count**, plus two for the anchor. This is the only honest
   figure. Use the largest bolt count in the sector.
2. **Estimated from the longest route** at roughly one bolt per 3 m, plus two.
   Mark estimates as estimates — a footnote saying which is which costs nothing.

Then reconcile the number against whatever the sector's gear paragraph says. If
the prose says "14 draws" and the table says 16, the reader cannot tell which to
believe, and that contradiction is yours, not a source's. Fix the prose.

Rope length follows the same logic: take the longest route, double it, and check
against the longest extension rather than the base route — extensions are exactly
where people get caught short. Flag anything needing more than a 70 m rope, and
flag descents needing two abseils or a single very long rope, which printed guides
often mention once and databases omit entirely.
