const express = require('express');
const axios = require('axios');
const cheerio = require('cheerio');

const app = express();
const PORT = process.env.PORT || 3000;

// Headers to look human to Cricbuzz
const FETCH_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Referer': 'https://www.cricbuzz.com/',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'en-US,en;q=0.9',
  'Accept-Encoding': 'gzip, deflate',
  'Connection': 'keep-alive',
};

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

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Get matches for a specific date
app.get('/cricket/date/:date', async (req, res) => {
  const dateStr = req.params.date; // Format: YYYY-MM-DD

  try {
    const cached = getFromCache(`matches-${dateStr}`);
    if (cached) {
      res.setHeader('X-Cache', 'HIT');
      return res.json(cached);
    }

    console.log(`[FETCHING] Matches for ${dateStr} from Cricbuzz`);

    // Convert date to Cricbuzz format (e.g., 28-03-2026)
    const [year, month, day] = dateStr.split('-');
    const cricbuzzDate = `${day}-${month}-${year}`;

    const response = await axios.get(`https://www.cricbuzz.com/cricket-match/schedule/${cricbuzzDate}`, {
      headers: FETCH_HEADERS,
      timeout: 10000,
    });

    const $ = cheerio.load(response.data);
    const matches = [];

    $('.cb-col-100.cb-col').each((index, element) => {
      try {
        const titleElement = $(element).find('.cb-lv-scr-mtch-hdr a');
        const title = titleElement.text().trim();
        const href = titleElement.attr('href');

        if (!href || !title) return;

        const matchIdMatch = href.match(/\/(\d+)\//);
        const matchId = matchIdMatch ? matchIdMatch[1] : null;

        if (!matchId) return;

        const teams = [];
        $(element).find('.cb-ovr-flo.cb-hmscg-tm-nm').each((i, teamEl) => {
          const teamName = $(teamEl).text().trim();
          const runElement = $(element).find('.cb-ovr-flo').filter(':not(.cb-hmscg-tm-nm)').eq(i);
          const runs = runElement.text().trim().split(teamName).join('').trim();
          teams.push({ name: teamName, score: runs });
        });

        const status = $(element).find('.cb-text-live').text().trim() ||
                      $(element).find('.cb-text-complete').text().trim() ||
                      $(element).find('.cb-text-schedule').text().trim() ||
                      'Scheduled';

        matches.push({
          match_id: matchId,
          match_title: title,
          teams: teams,
          status: status,
          date: dateStr,
          source: 'cricbuzz',
        });
      } catch (e) {
        console.error('Error parsing match:', e.message);
      }
    });

    const result = {
      date: dateStr,
      matches: matches,
      timestamp: new Date().toISOString(),
    };

    setCache(`matches-${dateStr}`, result);
    res.setHeader('X-Cache', 'MISS');
    res.json(result);
  } catch (error) {
    console.error(`[ERROR] Date ${dateStr} fetch failed:`, error.message);
    res.status(500).json({ error: `Failed to fetch matches for ${dateStr}: ${error.message}` });
  }
});

// Get IPL matches specifically
app.get('/cricket/ipl', async (req, res) => {
  try {
    const cached = getFromCache('ipl-matches');
    if (cached) {
      res.setHeader('X-Cache', 'HIT');
      return res.json(cached);
    }

    console.log('[FETCHING] IPL 2026 matches from Cricbuzz');
    const response = await axios.get('https://www.cricbuzz.com/cricket-match/ipl-2026', {
      headers: FETCH_HEADERS,
      timeout: 10000,
    });

    const $ = cheerio.load(response.data);
    const matches = [];

    $('.cb-col-100.cb-col').each((index, element) => {
      try {
        const titleElement = $(element).find('.cb-lv-scr-mtch-hdr a');
        const title = titleElement.text().trim();
        const href = titleElement.attr('href');

        if (!href || !title) return;

        const matchIdMatch = href.match(/\/(\d+)\//);
        const matchId = matchIdMatch ? matchIdMatch[1] : null;

        if (!matchId) return;

        const teams = [];
        $(element).find('.cb-ovr-flo.cb-hmscg-tm-nm').each((i, teamEl) => {
          const teamName = $(teamEl).text().trim();
          const runElement = $(element).find('.cb-ovr-flo').filter(':not(.cb-hmscg-tm-nm)').eq(i);
          const runs = runElement.text().trim().split(teamName).join('').trim();
          teams.push({ name: teamName, score: runs });
        });

        const status = $(element).find('.cb-text-live').text().trim() ||
                      $(element).find('.cb-text-complete').text().trim() ||
                      'Upcoming';

        matches.push({
          match_id: matchId,
          match_title: title,
          teams: teams,
          status: status,
          series: { name: 'IPL 2026' },
          source: 'cricbuzz',
        });
      } catch (e) {
        console.error('Error parsing IPL match:', e.message);
      }
    });

    const result = {
      matches: matches,
      timestamp: new Date().toISOString(),
    };

    setCache('ipl-matches', result);
    res.setHeader('X-Cache', 'MISS');
    res.json(result);
  } catch (error) {
    console.error('[ERROR] IPL matches fetch failed:', error.message);
    res.status(500).json({ error: `Failed to fetch IPL matches: ${error.message}` });
  }
});

// Get live matches from Cricbuzz
app.get('/cricket/live', async (req, res) => {
  try {
    const cached = getFromCache('live-matches');
    if (cached) {
      res.setHeader('X-Cache', 'HIT');
      return res.json(cached);
    }

    console.log('[FETCHING] Live matches from Cricbuzz');
    const response = await axios.get('https://www.cricbuzz.com/cricket-match/live-scores', {
      headers: FETCH_HEADERS,
      timeout: 10000,
    });

    const $ = cheerio.load(response.data);
    const matches = [];

    // Extract live matches from Cricbuzz
    $('.cb-col-100.cb-col').each((index, element) => {
      try {
        const titleElement = $(element).find('.cb-lv-scr-mtch-hdr a');
        const title = titleElement.text().trim();
        const href = titleElement.attr('href');

        if (!href) return;

        // Extract match ID from href like: /live-cricket-scores/1234567/
        const matchIdMatch = href.match(/\/(\d+)\//);
        const matchId = matchIdMatch ? matchIdMatch[1] : null;

        if (!matchId || !title) return;

        // Extract teams and scores
        const teams = [];
        $(element).find('.cb-ovr-flo.cb-hmscg-tm-nm').each((i, teamEl) => {
          const teamName = $(teamEl).text().trim();
          const runElement = $(element).find('.cb-ovr-flo').filter(':not(.cb-hmscg-tm-nm)').eq(i);
          const runs = runElement.text().trim().split(teamName).join('').trim();

          teams.push({
            name: teamName,
            score: runs,
          });
        });

        // Check if match is live or upcoming
        const status = $(element).find('.cb-text-live').text().trim() ||
                      $(element).find('.cb-text-complete').text().trim() ||
                      'Upcoming';

        // Get series/tournament name from title
        const seriesMatch = title.match(/,\s*([^,]+)$/);
        const series = seriesMatch ? seriesMatch[1].trim() : 'IPL';

        matches.push({
          match_id: matchId,
          match_title: title,
          teams: teams,
          status: status,
          series: {
            name: series,
          },
          source: 'cricbuzz',
        });
      } catch (e) {
        console.error('Error parsing match:', e.message);
      }
    });

    // Convert to ESPNcricinfo-like format for compatibility
    const result = {
      matches: matches,
      timestamp: new Date().toISOString(),
    };

    setCache('live-matches', result);
    res.setHeader('X-Cache', 'MISS');
    res.json(result);
  } catch (error) {
    console.error('[ERROR] Cricbuzz fetch failed:', error.message);
    res.status(500).json({ error: `Failed to fetch from Cricbuzz: ${error.message}` });
  }
});

// Get specific match details from Cricbuzz
app.get('/cricket/match/:id', async (req, res) => {
  const matchId = req.params.id;

  try {
    const cached = getFromCache(`match-${matchId}`);
    if (cached) {
      res.setHeader('X-Cache', 'HIT');
      return res.json(cached);
    }

    console.log(`[FETCHING] Match ${matchId} from Cricbuzz`);
    const matchUrl = `https://www.cricbuzz.com/live-cricket-scores/${matchId}`;
    const response = await axios.get(matchUrl, {
      headers: FETCH_HEADERS,
      timeout: 10000,
    });

    const $ = cheerio.load(response.data);

    // Extract match title
    const title = $('.cb-nav-hdr.cb-font-18').text().trim().replace(', Commentary', '');

    // Extract live score
    const liveScore = $('.cb-font-20.text-bold').text().trim();

    // Extract match status/update
    const update = $('.cb-col.cb-col-100.cb-min-stts.cb-text-complete').text().trim() ||
                  $('.cb-text-inprogress').text().trim() ||
                  $('.cb-text-stumps').text().trim() ||
                  'Match Update';

    // Extract current run rate
    const runRate = $('.cb-font-12.cb-text-gray').first().text().trim();

    // Extract batsmen
    const batsmanOne = {
      name: $('.cb-col.cb-col-50').eq(1).text().trim(),
      runs: $('.cb-col.cb-col-10.ab.text-right').eq(0).text().trim(),
      balls: $('.cb-col.cb-col-10.ab.text-right').eq(1).text().trim(),
    };

    const batsmanTwo = {
      name: $('.cb-col.cb-col-50').eq(2).text().trim(),
      runs: $('.cb-col.cb-col-10.ab.text-right').eq(2).text().trim(),
      balls: $('.cb-col.cb-col-10.ab.text-right').eq(3).text().trim(),
    };

    // Extract bowlers
    const bowlerOne = {
      name: $('.cb-col.cb-col-50').eq(4).text().trim(),
      overs: $('.cb-col.cb-col-10.text-right').eq(4).text().trim(),
      runs: $('.cb-col.cb-col-10.text-right').eq(5).text().trim(),
      wickets: $('.cb-col.cb-col-8.text-right').eq(5).text().trim(),
    };

    const bowlerTwo = {
      name: $('.cb-col.cb-col-50').eq(5).text().trim(),
      overs: $('.cb-col.cb-col-10.text-right').eq(6).text().trim(),
      runs: $('.cb-col.cb-col-10.text-right').eq(7).text().trim(),
      wickets: $('.cb-col.cb-col-8.text-right').eq(7).text().trim(),
    };

    // Extract commentary (last event)
    let commentary = 'No commentary yet';
    const commentElements = $('.cb-col-75.cb-lv-scrs-cmntry-txt');
    if (commentElements.length > 0) {
      commentary = commentElements.first().text().trim();
    }

    const result = {
      match_id: matchId,
      match: title,
      title: title,
      status: update,
      liveScore: liveScore,
      runRate: runRate,
      batsmen: {
        one: batsmanOne,
        two: batsmanTwo,
      },
      bowlers: {
        one: bowlerOne,
        two: bowlerTwo,
      },
      commentary: commentary,
      timestamp: new Date().toISOString(),
      source: 'cricbuzz',
    };

    setCache(`match-${matchId}`, result);
    res.setHeader('X-Cache', 'MISS');
    res.json(result);
  } catch (error) {
    console.error(`[ERROR] Match ${matchId} fetch failed:`, error.message);
    res.status(500).json({ error: `Failed to fetch match: ${error.message}` });
  }
});

// Error handling
app.use((err, req, res, next) => {
  console.error('[UNHANDLED ERROR]', err);
  res.status(500).json({ error: 'Internal server error' });
});

// Start server
app.listen(PORT, () => {
  console.log(`🏏 Cricbuzz proxy server running on port ${PORT}`);
  console.log(`Endpoints:`);
  console.log(`  Health: GET http://localhost:${PORT}/health`);
  console.log(`  Live matches: GET http://localhost:${PORT}/cricket/live`);
  console.log(`  IPL 2026: GET http://localhost:${PORT}/cricket/ipl`);
  console.log(`  Date-specific: GET http://localhost:${PORT}/cricket/date/YYYY-MM-DD`);
  console.log(`  Match details: GET http://localhost:${PORT}/cricket/match/{id}`);
});
