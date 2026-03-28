const express = require('express');
const fetch = require('node-fetch');

const app = express();
const PORT = process.env.PORT || 3000;

// Headers to look human to ESPNcricinfo
const FETCH_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Referer': 'https://www.espncricinfo.com/',
  'Origin': 'https://www.espncricinfo.com',
  'Accept': 'application/json',
  'Accept-Language': 'en-US,en;q=0.9',
  'Accept-Encoding': 'gzip, deflate, br',
  'Sec-Fetch-Dest': 'empty',
  'Sec-Fetch-Mode': 'cors',
  'Sec-Fetch-Site': 'same-origin',
  'Cache-Control': 'no-cache',
  'DNT': '1',
  'Connection': 'keep-alive',
};

// Simple in-memory cache (auto-clears every 60 seconds)
const cache = {};
const CACHE_TTL = 60000; // 60 seconds

function getCacheKey(url) {
  return `cache:${url}`;
}

function getFromCache(url) {
  const key = getCacheKey(url);
  const cached = cache[key];
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.data;
  }
  delete cache[key];
  return null;
}

function setCache(url, data) {
  const key = getCacheKey(url);
  cache[key] = {
    data,
    timestamp: Date.now(),
  };
}

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Proxy endpoint for live matches
app.get('/cricket/live', async (req, res) => {
  const url = 'https://www.espncricinfo.com/matches/engine/match/live.json';

  try {
    // Check cache first
    const cached = getFromCache(url);
    if (cached) {
      console.log('[CACHE HIT] Live matches');
      res.setHeader('X-Cache', 'HIT');
      return res.json(cached);
    }

    console.log('[FETCHING] Live matches from ESPNcricinfo');
    const response = await fetch(url, {
      headers: FETCH_HEADERS,
      timeout: 10000,
    });

    if (!response.ok) {
      console.error(`[ERROR] ESPNcricinfo returned ${response.status}`);
      return res.status(response.status).json({
        error: `ESPNcricinfo returned ${response.status}`,
      });
    }

    const data = await response.json();
    setCache(url, data);
    res.setHeader('X-Cache', 'MISS');
    res.json(data);
  } catch (error) {
    console.error('[ERROR]', error.message);
    res.status(500).json({ error: error.message });
  }
});

// Proxy endpoint for specific match
app.get('/cricket/match/:id', async (req, res) => {
  const matchId = req.params.id;
  const url = `https://www.espncricinfo.com/matches/engine/match/${matchId}/live.json`;

  try {
    // Check cache first
    const cached = getFromCache(url);
    if (cached) {
      console.log(`[CACHE HIT] Match ${matchId}`);
      res.setHeader('X-Cache', 'HIT');
      return res.json(cached);
    }

    console.log(`[FETCHING] Match ${matchId} from ESPNcricinfo`);
    const response = await fetch(url, {
      headers: FETCH_HEADERS,
      timeout: 10000,
    });

    if (!response.ok) {
      console.error(`[ERROR] ESPNcricinfo returned ${response.status} for match ${matchId}`);
      return res.status(response.status).json({
        error: `ESPNcricinfo returned ${response.status}`,
      });
    }

    const data = await response.json();
    setCache(url, data);
    res.setHeader('X-Cache', 'MISS');
    res.json(data);
  } catch (error) {
    console.error(`[ERROR] Match ${matchId}:`, error.message);
    res.status(500).json({ error: error.message });
  }
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('[UNHANDLED ERROR]', err);
  res.status(500).json({ error: 'Internal server error' });
});

// Start server
app.listen(PORT, () => {
  console.log(`🏏 Cricket proxy server running on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
  console.log(`Live matches: GET http://localhost:${PORT}/cricket/live`);
  console.log(`Match details: GET http://localhost:${PORT}/cricket/match/{id}`);
});
