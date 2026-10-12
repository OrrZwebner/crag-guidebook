# crag-guidebook

A skill that turns everything known about a climbing crag — databases, photos of a printed guidebook, your own visit notes — into a printable guidebook with shade times for every sector, plus map files for your phone.

## Install

1. Go to this repository's **Releases** and download **`crag-guidebook.zip`**:
   https://github.com/OrrZwebner/crag-guidebook/releases/latest/download/crag-guidebook.zip
   Don't unzip it.
2. Upload it in your AI app's skills settings. In the Claude app: **Settings → Capabilities → Skills → Upload skill**, choose the file, and make sure the skill is switched on. Other AI apps that support skills work the same way: upload the zip where they manage skills.

Don't use the green **Code → Download ZIP** button — that gives you the whole repository, which the app won't recognise as a skill.

## Use

Start a new chat and ask, for example:

- "Make me a mini guide for <crag name> — I'm going in June."
- "Here are photos of the guidebook pages. The sources disagree — sort them out and tell me when each sector is in the shade."
- "Add my notes and photos from my visit to the guide you made last time."

Optional: if your AI app can connect MCP servers, connecting OpenBeta (https://github.com/jacKlinc/openbeta-mcp) gives it extra route data.

You get back the guide as a PDF — or, if the app can't make PDFs, an HTML file: open it in your browser, choose **Print → Save as PDF** (A4, background graphics on). You also get map files (KML for Google Earth or My Maps, GPX for a phone GPS app, and a CSV spreadsheet) and the guide's source file, so it can be updated later.

Shade times are calculated and approximate; the guide says so, and prints first-hand observations instead where someone has checked.

When a crag has more routes than a guide can print, it keeps every route the community rates ★★ or better, at any grade — never a selection by grade or by popularity — and says how many it left out. Sectors are never dropped for their season; shady ones are included with their conditions printed.

The printed maps show the real surroundings from OpenStreetMap (roads, tracks, paths, cliffs, water, buildings, parking) under numbered sector pins, and flag any sector whose shade aspect disagrees with the mapped cliff.

## License

MIT — see [LICENSE](LICENSE).
