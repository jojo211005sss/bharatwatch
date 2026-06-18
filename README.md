# BharatWatch

A searchable, visual **public-data knowledge graph** for surfacing potential corruption
patterns in Indian politics — politicians, declared assets, family ties, companies (MCA),
government contracts (CPPP/GeM) and fund flows (PFMS), linked by PAN / DIN / CIN and
AI-assisted name resolution. Inspired by Bruno César's Brazilian public-spending graph.

> **Disclaimer:** For transparency and informational purposes only — not legal advice or an
> accusation of wrongdoing. Flags are statistical indicators requiring human verification.
> This repo ships with **entirely fictional seed data** for demonstration.

## Run

```sh
python3 app/server.py
# → http://127.0.0.1:8787   (admin password: bharat-admin)
```

No dependencies — Python 3.9+ standard library only (SQLite included). The graph view loads
Cytoscape.js from a CDN; everything else works offline.

Optional environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `BHARATWATCH_PORT` | `8787` | HTTP port |
| `BHARATWATCH_ADMIN_PASSWORD` | `bharat-admin` | Admin portal password |
| `BHARATWATCH_DB` | `data/bharatwatch.db` | SQLite path |
| `ANTHROPIC_API_KEY` | — | Enables Claude (`claude-opus-4-8`) adjudication of grey-zone entity matches (`pip install anthropic`) |

## Architecture

```
app/
  server.py    stdlib HTTP server + JSON API + static files
  db.py        SQLite schema (entities, declarations, contracts, fund_flows,
               relationships, flags, review_queue, imports)
  scoring.py   rule engine: FAMILY_CONTRACT, ASSET_GROWTH, REPEATED_AWARDS,
               GHOST_ENTITY, FUND_LOOP → risk % + explanation + evidence
  resolve.py   entity resolution: PAN > DIN > CIN > fuzzy name (+optional Claude)
  importer.py  CSV ingestion for 6 dataset shapes + manual review queue
  seed.py      fictional demo data
public/        dashboard, entity profile (Cytoscape graph, timeline, exports),
               explore, national overview, about, admin
sample_data/   example CSVs to test the admin importer
```

## Key flows

- **Search → profile** — name/PAN/DIN/CIN/constituency search; profile shows summary card,
  interactive L1–L3 relationship graph (click nodes to drill down, edges for evidence),
  flagged insights with risk %, timeline, linked-data tabs, and PDF/CSV/JSON/PNG exports.
- **Admin ingestion** (`/admin`) — upload CSVs from ECI/MCA/CPPP/GeM/PFMS exports; rows are
  normalized and entity-resolved; uncertain matches land in a review queue; detection
  re-runs automatically after every import.
- **Detection** — pure-SQL/graph rules with value-scaled scores (see `app/scoring.py`).
  Re-run anytime with `python3 app/scoring.py` or the admin "Re-run detection" button.

## API (read-only public)

`/api/stats` · `/api/search?q=` · `/api/entities?type=&state=&q=` · `/api/entity/{id}` ·
`/api/graph/{id}?depth=1..4` · `/api/highrisk` · `/api/overview` ·
`/api/export/entity/{id}.json|.csv`

Admin (token via `POST /api/admin/login`): `/api/admin/upload`, `/api/admin/review`,
`/api/admin/rescore`, `/api/admin/imports`.

## Data sources (production ingestion)

ECI affidavit portal / MyNeta (ADR) · MCA master data & data.gov.in bulk CSVs ·
CPPP eProcure · GeM · PFMS dashboards · CVC lists · GST public search · state portals.
All public; no scraping of restricted sources.
