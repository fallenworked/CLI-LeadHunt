# LEAD HUNTER — LOCAL EDITION

**English** · [Русский](README.md)

A local terminal lead hunter for Windows 10/11. It finds real OpenStreetMap POIs
through the public Overpass API, stores them in SQLite, keeps statuses and notes,
and exports CSV plus a standalone HTML report.

No server, account, subscription, Cloudflare Worker/D1, or installer.
Everything runs from the console:

```powershell
python main.py
```

```
LEAD HUNTER · LOCAL EDITION
"Every lead found is a new opportunity"
```

## Features

- Dark terminal UI: graphite, blood-red accents, an ASCII Grim Reaper, live progress.
- Real OpenStreetMap search: city, niche, keywords, radius, limit, and filters
  for phone, address, and businesses with websites.
- Multiple Overpass mirrors are queried in parallel. A failed mirror is reported
  and never crashes the search.
- SQLite storage: leads, search history, lead-to-search links, settings, and a
  geocoding cache for cities.
- Deduplication within and across searches by name, coordinates, phone, or
  address. User statuses and notes are never overwritten.
- Status pipeline: new, contacted, interested, proposal, customer, rejected.
- Lead browser with filters, pagination, detail view, maps, notes, and deletion.
- Search history: run details, errors, rerun with the same parameters, export.
- CSV export (UTF-8 BOM, `;` delimiter for Excel) and a standalone dark-theme
  HTML report with search, filters, sorting, and statistics. The report works
  offline.
- Source management: real mirror checks, add/remove/reset mirrors, enable or
  disable OSM.
- Statistics for the database, statuses, cities, niches, and 7-day activity.
- CLI modes for automation and checks without the interactive menu.

## Installation

Python 3.10+ is required (tested on 3.12), plus internet access for searches.

```powershell
cd lead-hunter-main
python -m pip install -r requirements.txt
python main.py
```

Dependencies: `rich` (terminal UI), `questionary` (menus and input), and
`requests` (Overpass, Photon, Nominatim). Nothing else is needed.

## Usage

### Interactive mode

```powershell
python main.py
```

Main menu:

1. Start a lead search.
2. Saved leads.
3. Search saved leads.
4. Search history.
5. CSV / HTML export.
6. Source management.
7. Settings.
8. Statistics.
9. Exit.

`Ctrl+C` goes back inside prompts and exits from the main menu.
Arrow keys and `Enter` work in every menu.

### Search without the menu

```powershell
python main.py --search "Moscow" --niche "dentistry" --radius 3000 --limit 120
python main.py --search "Kazan" --niche "cafe" --format both
python main.py --city "Sochi" --niche "hotel" --only-phone
```

Useful flags:

| Flag | Purpose |
| --- | --- |
| `--search CITY` | run a search and exit |
| `--city CITY` | alternative way to pass the city |
| `--niche NICHE` | niche from the dictionary or a custom keyword |
| `--keywords "a,b"` | additional comma-separated keywords |
| `--radius 5000` | search radius in metres (500–20000) |
| `--limit 250` | maximum number of leads (10–1000) |
| `--only-phone` | only leads with a phone number |
| `--require-address` | only leads with an address |
| `--include-website` | keep businesses that have a website |
| `--format csv\|html\|both` | export the result after the search |
| `--check` | check Overpass mirror availability |
| `--no-anim` | skip the startup animation |
| `--version` | print the version |

### Source check

```powershell
python main.py --check
```

The command sends real requests to the mirrors and reports HTTP errors,
timeouts, and latency. It never reports "online" without a network response.

## Where data is stored

| Item | Location |
| --- | --- |
| SQLite database | `data/lead_hunter.db` |
| Error log | `data/lead_hunter.log` |
| Default exports | `results/` |

Directories are created automatically. Paths can be overridden with the
`LH_DATA_DIR`, `LH_DB_PATH`, and `LH_RESULTS_DIR` environment variables.

## How search works

1. The city is looked up in a local dictionary (60+ cities). Unknown cities are
   geocoded through Photon, then Nominatim; coordinates are cached.
2. An Overpass query is built from the selected niche tags, or from the name
   for a custom keyword. The selected radius defines the bounding box.
3. Overpass mirrors are queried in parallel; the first non-empty response wins,
   and all other errors are included in the report.
4. Name, phone, email, address, opening hours, website, social contacts,
   business type, and coordinates are extracted from OSM tags. Objects without
   a name are discarded.
5. Filters run before saving; by default, businesses with a website are
   excluded.
6. Deduplication: name + coordinates (~100 m), otherwise name + phone, address,
   or city.
7. Results are saved to SQLite and linked to the search history record. A
   repeated search fills in missing fields but does not touch status or notes.

## Niches

25 niches are built in: dentistry, cafe, restaurant, hairdresser, beauty salon,
auto repair, pharmacy, fitness, lawyer, car wash, clothing store, bakery,
flowers, furniture, pet store, optician, hotel, veterinary clinic, bar,
bookstore, jewellery, pizzeria/fast food, cinema, pool/sports centre, and
tattoo studio.

For anything else, choose "Other niche / keyword": the search will match names
in OSM.

## Source and limitations

The only working source is **OpenStreetMap / Overpass**. The previous version of
the project also used only this source. Google Places, Yandex Maps, and 2GIS
require API keys, contracts, or commercial terms, so they are not simulated.

Source rules are respected:

- a dedicated application `User-Agent`;
- a configurable minimum interval between searches;
- Overpass timeouts and limits;
- OSM data is distributed under the ODbL licence; when publishing, credit
  "© OpenStreetMap contributors".

Public mirrors sometimes return `502`, `429`, or a timeout. This is normal: the
app reports the error, tries other mirrors, and never replaces results with
invented leads.

## Removed from the old version

- Cloudflare Worker, D1, migrations, and `wrangler`;
- web UI, static assets, and server APIs;
- Google/Telegram OAuth, demo login, and accounts;
- subscriptions, payments, and legal pages;
- cron/auto-search and the Telegram bot;
- AI chat on external APIs (Gemini/DeepSeek).

Those features depended on cloud services, secrets, and payment providers. They
are gone from the local version, but its core value is preserved and improved:
real lead search, storage, history, statuses, and export.

## Project structure

```
main.py                 CLI and entry point
config.py               paths, version, default settings

core/
  dictionaries.py       cities, countries, niches, OSM tags
  models.py             Lead, CityInfo, SearchParams, SearchStats
  geocoder.py           dictionary + Photon + Nominatim + cache
  parser.py             Overpass query, OSM parsing
  filters.py            filters and rejection reasons
  deduplicator.py       matching keys and fingerprint
  engine.py             search and save orchestration
  settings.py           typed settings
  utils.py              dates, links, normalisation

database/storage.py     SQLite schema and queries
sources/                Overpass source, mirror checks, registry
exporters/              CSV and standalone HTML
ui/                     theme, ASCII Reaper, menu, widgets, screens
tests/                  network-free unittest suite

data/                   created on first run
results/                created on first run
```

## Tests

```powershell
python -m unittest discover -s tests -v
```

Covered: OSM parsing, filters, deduplication, dictionary geocoding, SQLite
storage, cross-search deduplication, source error isolation, CSV/HTML export,
and HTML escaping. The tests do not access the network.

Live source check:

```powershell
python main.py --check
python main.py --search "Moscow" --niche "cafe" --radius 1200 --limit 20
```

## Troubleshooting

- All screen and search errors are written to `data/lead_hunter.log`.
- If a city is not found, check the spelling or use the nearest major city.
- If every mirror is unavailable, check internet/firewall, open
  "Source management" → "Check mirrors", and add another Overpass mirror if
  needed.
- If the terminal has no colours or borders, use Windows Terminal or enable VT
  support; the app already tries to enable UTF-8 and ANSI automatically.

## Data licence

OpenStreetMap data: © OpenStreetMap contributors, ODbL.
This project is not affiliated with the OpenStreetMap Foundation.
