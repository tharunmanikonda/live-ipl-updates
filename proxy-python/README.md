# Cricket Python Proxy

A Flask-based HTTP API proxy that scrapes Cricbuzz for live cricket data using BeautifulSoup.

## Endpoints

- `GET /health` - Health check
- `GET /cricket/live` - All live matches
- `GET /cricket/ipl` - IPL 2026 matches
- `GET /cricket/match/{id}` - Match details
- `GET /cricket/date/{date}` - Matches for specific date (YYYY-MM-DD)

## Installation

```bash
pip install -r requirements.txt
```

## Run

```bash
PORT=3000 python server.py
```

Or with gunicorn for production:

```bash
gunicorn -w 2 -b 0.0.0.0:3000 server:app
```

## Why Python?

- **BeautifulSoup**: More mature for HTML parsing
- **Proven Cricbuzz selectors**: Based on working code
- **Better error handling**: Inherits from MCP server reference
- **Lighter than full MCP**: Just the scraping logic
