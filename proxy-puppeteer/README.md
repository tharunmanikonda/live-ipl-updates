# Cricket Puppeteer Proxy

A Node.js Express API proxy that scrapes Cricbuzz using Puppeteer for JavaScript rendering.

## Why Puppeteer?

Cricbuzz dynamically loads match content with JavaScript. Puppeteer actually renders the page in a headless browser, so we can see the full DOM with all dynamic content.

## Endpoints

- `GET /health` - Health check
- `GET /cricket/live` - All live matches
- `GET /cricket/ipl` - IPL 2026 matches
- `GET /cricket/match/{id}` - Match details

## Installation

```bash
npm install
```

## Run

```bash
PORT=3000 npm start
```

Or with PM2:

```bash
pm2 start server.js --name cricket-proxy-puppeteer
```

## Performance

- First request: ~5-10 seconds (browser startup + page render)
- Cached requests: <100ms
- Cache TTL: 60 seconds

## Requirements

- Node.js 18+
- ~500MB disk space (Chromium binary)
