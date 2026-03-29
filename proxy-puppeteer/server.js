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

    // Scroll to load more matches (infinite scroll)
    console.log('[SCROLLING] Loading more matches...');
    for (let i = 0; i < 5; i++) {
      await page.evaluate(() => {
        window.scrollBy(0, window.innerHeight);
      });
      await new Promise(resolve => setTimeout(resolve, 800));
      console.log(`[SCROLL ${i + 1}/5] Loaded more matches`);
    }

    // Extract all matches using Puppeteer
    const matches = await page.evaluate(() => {
      const matchLinks = document.querySelectorAll('a[class*="block"][class*="mb-3"]');
      const matches = [];
      const seenIds = new Set();

      matchLinks.forEach(link => {
        try {
          const href = link.getAttribute('href');
          if (!href || !href.includes('/live-cricket-scores/')) return;

          // Extract match ID from href: /live-cricket-scores/{id}/...
          const matchIdMatch = href.match(/\/live-cricket-scores\/(\d+)\//);
          if (!matchIdMatch) return;

          const matchId = matchIdMatch[1];

          // Skip duplicates
          if (seenIds.has(matchId)) return;
          seenIds.add(matchId);

          // Get title and status from title attribute
          const fullTitle = link.getAttribute('title');
          if (!fullTitle) return;

          // Parse status from title: "Team1 vs Team2, Match - Status"
          let status = 'Scheduled';
          const statusMatch = fullTitle.match(/ - (.+)$/);
          if (statusMatch) {
            status = statusMatch[1];
          }

          // Get match teams from inner div
          const teamsDiv = link.querySelector('div[class*="text-white"]');
          const title = teamsDiv ? teamsDiv.textContent.trim() : fullTitle;

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

    // Scroll to load more matches (infinite scroll)
    console.log('[SCROLLING] Loading more IPL matches...');
    for (let i = 0; i < 5; i++) {
      await page.evaluate(() => {
        window.scrollBy(0, window.innerHeight);
      });
      await new Promise(resolve => setTimeout(resolve, 800));
      console.log(`[SCROLL ${i + 1}/5] Loaded more IPL matches`);
    }

    // Extract all matches using Puppeteer
    const matches = await page.evaluate(() => {
      const matchLinks = document.querySelectorAll('a[class*="block"][class*="mb-3"]');
      const matches = [];
      const seenIds = new Set();

      matchLinks.forEach(link => {
        try {
          const href = link.getAttribute('href');
          if (!href || !href.includes('/live-cricket-scores/')) return;

          // Extract match ID from href: /live-cricket-scores/{id}/...
          const matchIdMatch = href.match(/\/live-cricket-scores\/(\d+)\//);
          if (!matchIdMatch) return;

          const matchId = matchIdMatch[1];

          // Skip duplicates
          if (seenIds.has(matchId)) return;
          seenIds.add(matchId);

          // Get title and status from title attribute
          const fullTitle = link.getAttribute('title');
          if (!fullTitle) return;

          // Parse status from title: "Team1 vs Team2, Match - Status"
          let status = 'Scheduled';
          const statusMatch = fullTitle.match(/ - (.+)$/);
          if (statusMatch) {
            status = statusMatch[1];
          }

          // Get match teams from inner div
          const teamsDiv = link.querySelector('div[class*="text-white"]');
          const title = teamsDiv ? teamsDiv.textContent.trim() : fullTitle;

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
      // Extract match result
      const resultEl = document.querySelector('div[class*="text-cbTextLink"]');
      const matchResult = resultEl ? resultEl.textContent.trim() : 'Match ongoing';

      // Extract team scores
      const teamScores = [];
      const scoreDivs = document.querySelectorAll('div[class*="flex flex-row text-cbTxtSec"]');

      scoreDivs.forEach(scoreDiv => {
        try {
          const teamEl = scoreDiv.querySelector('div');
          if (teamEl) {
            const teamName = teamEl.textContent.trim();
            const scoreText = scoreDiv.textContent.trim().replace(teamName, '').trim();
            if (scoreText && (scoreText.includes('/') || /\d/.test(scoreText))) {
              teamScores.push({
                team: teamName,
                score: scoreText
              });
            }
          }
        } catch (e) {
          console.debug('Error parsing team score:', e.message);
        }
      });

      // Extract player of the match
      const potmEl = document.querySelector('a[title*="View Profile"]');
      const playerOfMatch = potmEl ? potmEl.textContent.trim() : null;

      return {
        result: matchResult,
        scores: teamScores,
        playerOfMatch: playerOfMatch
      };
    });

    await page.close();

    const result = {
      match_id: matchId,
      url: `https://www.cricbuzz.com/live-cricket-scores/${matchId}`,
      result: matchData.result,
      scores: matchData.scores,
      player_of_match: matchData.playerOfMatch,
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

// Get over-by-over data
app.get('/cricket/overs/:id', async (req, res) => {
  const matchId = req.params.id;
  const cached = getFromCache(`overs-${matchId}`);
  if (cached) {
    return res.json({ ...cached, cache: 'HIT' });
  }

  try {
    console.log(`[FETCHING] Overs for match ${matchId} using Puppeteer`);
    const browser = await initBrowser();
    const page = await browser.newPage();

    await page.goto(`https://www.cricbuzz.com/live-cricket-over-by-over/${matchId}`, {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    const oversData = await page.evaluate(() => {
      const overs = [];
      // Look for over/ball containers
      const overElements = document.querySelectorAll('div[class*="over"], div[class*="ball"]');

      overElements.forEach((elem, idx) => {
        try {
          const text = elem.textContent.trim();
          if (text && /\d+\.\d+/.test(text) && idx < 50) {
            overs.push({ text: text.substring(0, 500) });
          }
        } catch (e) {
          console.debug('Error parsing over:', e.message);
        }
      });

      return overs;
    });

    await page.close();

    const result = {
      match_id: matchId,
      url: `https://www.cricbuzz.com/live-cricket-over-by-over/${matchId}`,
      overs: oversData,
      timestamp: new Date().toISOString(),
      cache: 'MISS',
      count: oversData.length
    };

    setCache(`overs-${matchId}`, result);
    res.json(result);
  } catch (error) {
    console.error(`Error fetching overs for match ${matchId}:`, error.message);
    res.status(500).json({ error: error.message, overs: [] });
  }
});

// Get ball-by-ball commentary
app.get('/cricket/commentary/:id', async (req, res) => {
  const matchId = req.params.id;
  const cached = getFromCache(`commentary-${matchId}`);
  if (cached) {
    return res.json({ ...cached, cache: 'HIT' });
  }

  try {
    console.log(`[FETCHING] Commentary for match ${matchId} using Puppeteer`);
    const browser = await initBrowser();
    const page = await browser.newPage();

    await page.goto(`https://www.cricbuzz.com/live-cricket-full-commentary/${matchId}`, {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    const commentaryData = await page.evaluate(() => {
      const commentary = [];
      // Look for commentary/ball containers
      const commElements = document.querySelectorAll('div[class*="comment"], div[class*="ball"]');

      commElements.forEach((elem, idx) => {
        try {
          const text = elem.textContent.trim();
          // Look for ball references (over.ball format)
          const ballMatch = text.match(/(\d+)\.(\d+)/);
          if (ballMatch && text.length > 5 && idx < 100) {
            commentary.push({
              ball: `${ballMatch[1]}.${ballMatch[2]}`,
              text: text.substring(0, 500)
            });
          }
        } catch (e) {
          console.debug('Error parsing commentary:', e.message);
        }
      });

      return commentary;
    });

    await page.close();

    const result = {
      match_id: matchId,
      url: `https://www.cricbuzz.com/live-cricket-full-commentary/${matchId}`,
      commentary: commentaryData,
      timestamp: new Date().toISOString(),
      cache: 'MISS',
      count: commentaryData.length
    };

    setCache(`commentary-${matchId}`, result);
    res.json(result);
  } catch (error) {
    console.error(`Error fetching commentary for match ${matchId}:`, error.message);
    res.status(500).json({ error: error.message, commentary: [] });
  }
});

// Debug endpoint to inspect page structure
app.get('/debug/live', async (req, res) => {
  try {
    console.log('[DEBUG] Inspecting live matches page structure...');
    const browser = await initBrowser();
    const page = await browser.newPage();

    await page.goto('https://www.cricbuzz.com/cricket-match/live-scores', {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    // Try multiple selectors and report results
    const debug = await page.evaluate(() => {
      const results = {};

      // Test different selectors
      const selectors = [
        'a[class*="block"][class*="mb-3"]',
        'a[class*="block"]',
        'a[href*="/live-cricket-scores/"]',
        'div[class*="cb-mtch"]',
        'div[class*="match"]',
        '[class*="match"][class*="card"]',
        'a'
      ];

      selectors.forEach(selector => {
        const els = document.querySelectorAll(selector);
        results[selector] = {
          count: els.length,
          sample: els.length > 0 ? {
            classList: els[0].className,
            html: els[0].outerHTML.substring(0, 300),
            href: els[0].href || els[0].getAttribute('href') || 'no href',
            title: els[0].title || els[0].getAttribute('title') || 'no title'
          } : null
        };
      });

      // Get all links with cricket match IDs
      const allLinks = document.querySelectorAll('a[href*="/live-cricket-scores/"]');
      const matchLinks = [];
      allLinks.forEach((link, idx) => {
        if (idx < 5) {
          matchLinks.push({
            href: link.href,
            title: link.title,
            text: link.textContent.substring(0, 100),
            className: link.className
          });
        }
      });

      return {
        page: 'https://www.cricbuzz.com/cricket-match/live-scores',
        selectors: results,
        matchLinksFound: allLinks.length,
        sampleMatchLinks: matchLinks,
        bodyClass: document.body.className,
        documentHTML: document.documentElement.innerHTML.substring(0, 500)
      };
    });

    await page.close();
    res.json(debug);
  } catch (error) {
    console.error('Debug error:', error.message);
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
  console.log(`  Overs: GET http://localhost:${PORT}/cricket/overs/{id}`);
  console.log(`  Commentary: GET http://localhost:${PORT}/cricket/commentary/{id}`);
});
