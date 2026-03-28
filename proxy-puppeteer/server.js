const express = require('express');
const puppeteer = require('puppeteer');

const app = express();
const PORT = process.env.PORT || 3000;

let browser;

// Cache for 60 seconds
const cache = {};
const CACHE_TTL = 60000;

function getFromCache(key) {
  if (cache[key] && Date.now() - cache[key].timestamp < CACHE_TTL) {
    return cache[key].data;
  }
  delete cache[key];
  return null;
}

function setCache(key, data) {
  cache[key] = { data, timestamp: Date.now() };
}

// Initialize browser
async function initBrowser() {
  if (!browser) {
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
  }
  return browser;
}

app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Get live matches
app.get('/cricket/live', async (req, res) => {
  const cached = getFromCache('live-matches');
  if (cached) {
    return res.json({ ...cached, cache: 'HIT' });
  }

  try {
    console.log('[FETCHING] Live matches from Cricbuzz using Puppeteer');
    const browser = await initBrowser();
    const page = await browser.newPage();

    await page.goto('https://www.cricbuzz.com/cricket-match/live-scores', {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    // Extract matches using Puppeteer
    const matches = await page.evaluate(() => {
      const matchElements = document.querySelectorAll('[class*="cb-mtch-lst"]');
      const matches = [];

      matchElements.forEach(el => {
        try {
          const link = el.querySelector('a[class*="text-hvr-underline"]');
          if (!link) return;

          const title = link.textContent.trim();
          const href = link.getAttribute('href');

          if (!title || !href) return;

          // Extract match ID from href
          const matchIdMatch = href.match(/\/(\d+)/);
          const matchId = matchIdMatch ? matchIdMatch[1] : null;

          if (!matchId) return;

          // Get status
          const statusEl = el.querySelector('[class*="cb-text-live"], [class*="cb-text-complete"]');
          const status = statusEl ? statusEl.textContent.trim() : 'Scheduled';

          matches.push({
            match_id: matchId,
            title: title,
            url: 'https://www.cricbuzz.com' + href,
            status: status,
            source: 'cricbuzz'
          });
        } catch (e) {
          console.error('Error parsing match:', e.message);
        }
      });

      return matches;
    });

    await page.close();

    const result = {
      matches: matches,
      timestamp: new Date().toISOString(),
      cache: 'MISS',
      count: matches.length
    };

    setCache('live-matches', result);
    res.json(result);
  } catch (error) {
    console.error('Error fetching live matches:', error.message);
    res.status(500).json({ error: error.message, matches: [] });
  }
});

// Get IPL matches
app.get('/cricket/ipl', async (req, res) => {
  const cached = getFromCache('ipl-matches');
  if (cached) {
    return res.json({ ...cached, cache: 'HIT' });
  }

  try {
    console.log('[FETCHING] IPL 2026 matches using Puppeteer');
    const browser = await initBrowser();
    const page = await browser.newPage();

    await page.goto('https://www.cricbuzz.com/cricket-series/9241/indian-premier-league-2026/matches', {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    // Extract matches using Puppeteer
    const matches = await page.evaluate(() => {
      const matchElements = document.querySelectorAll('[class*="cb-mtch-lst"]');
      const matches = [];

      matchElements.forEach(el => {
        try {
          const link = el.querySelector('a[class*="text-hvr-underline"]');
          if (!link) return;

          const title = link.textContent.trim();
          const href = link.getAttribute('href');

          if (!title || !href) return;

          // Extract match ID
          const matchIdMatch = href.match(/\/(\d+)/);
          const matchId = matchIdMatch ? matchIdMatch[1] : null;

          if (!matchId) return;

          // Get status
          const statusEl = el.querySelector('[class*="cb-text-live"], [class*="cb-text-complete"]');
          const status = statusEl ? statusEl.textContent.trim() : 'Scheduled';

          matches.push({
            match_id: matchId,
            title: title,
            url: 'https://www.cricbuzz.com' + href,
            status: status,
            series: 'IPL 2026',
            source: 'cricbuzz'
          });
        } catch (e) {
          console.error('Error parsing IPL match:', e.message);
        }
      });

      return matches;
    });

    await page.close();

    const result = {
      matches: matches,
      timestamp: new Date().toISOString(),
      cache: 'MISS',
      count: matches.length
    };

    setCache('ipl-matches', result);
    res.json(result);
  } catch (error) {
    console.error('Error fetching IPL matches:', error.message);
    res.status(500).json({ error: error.message, matches: [] });
  }
});

// Get specific match
app.get('/cricket/match/:id', async (req, res) => {
  const matchId = req.params.id;
  const cached = getFromCache(`match-${matchId}`);
  if (cached) {
    return res.json({ ...cached, cache: 'HIT' });
  }

  try {
    console.log(`[FETCHING] Match ${matchId} using Puppeteer`);
    const browser = await initBrowser();
    const page = await browser.newPage();

    await page.goto(`https://www.cricbuzz.com/live-cricket-scores/${matchId}`, {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    // Extract match details
    const matchData = await page.evaluate(() => {
      const titleEl = document.querySelector('h1');
      const title = titleEl ? titleEl.textContent.trim() : 'Match';

      const scoreEl = document.querySelector('[class*="cb-font-20"]');
      const score = scoreEl ? scoreEl.textContent.trim() : 'N/A';

      return { title, score };
    });

    await page.close();

    const result = {
      match_id: matchId,
      title: matchData.title,
      score: matchData.score,
      timestamp: new Date().toISOString(),
      cache: 'MISS'
    };

    setCache(`match-${matchId}`, result);
    res.json(result);
  } catch (error) {
    console.error(`Error fetching match ${matchId}:`, error.message);
    res.status(500).json({ error: error.message });
  }
});

// Cleanup
process.on('SIGINT', async () => {
  if (browser) {
    await browser.close();
  }
  process.exit(0);
});

app.listen(PORT, () => {
  console.log(`🏏 Puppeteer Cricket Proxy running on port ${PORT}`);
  console.log(`Endpoints:`);
  console.log(`  Health: GET http://localhost:${PORT}/health`);
  console.log(`  Live matches: GET http://localhost:${PORT}/cricket/live`);
  console.log(`  IPL 2026: GET http://localhost:${PORT}/cricket/ipl`);
  console.log(`  Match details: GET http://localhost:${PORT}/cricket/match/{id}`);
});
