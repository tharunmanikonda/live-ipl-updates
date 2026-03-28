// Headers to bypass ESPNcricinfo bot detection
const FETCH_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
  'Referer': 'https://www.espncricinfo.com/',
  'Origin': 'https://www.espncricinfo.com',
  'Accept': 'application/json',
  'Accept-Language': 'en-US,en;q=0.9',
  'Accept-Encoding': 'gzip, deflate, br',
  'Sec-Fetch-Dest': 'empty',
  'Sec-Fetch-Mode': 'cors',
  'Sec-Fetch-Site': 'same-origin',
  'Cache-Control': 'no-cache',
  'Pragma': 'no-cache',
  'DNT': '1',
  'Connection': 'keep-alive',
  'Upgrade-Insecure-Requests': '1',
  'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120"',
  'Sec-Ch-Ua-Mobile': '?0',
  'Sec-Ch-Ua-Platform': '"macOS"',
};

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(handleScheduled(event, env));
  },
};

async function handleScheduled(event, env) {
  const POKE_WEBHOOK = env.POKE_WEBHOOK_URL;
  const TOURNAMENT_FILTER = env.TOURNAMENT_FILTER || 'IPL'; // e.g., 'IPL', 'T20WC', 'ODI'
  const PROXY_URL = env.PROXY_URL || 'https://cricket-proxy-production.up.railway.app';
  const KV = env.CRICKET_STATE;

  if (!POKE_WEBHOOK) {
    console.error('POKE_WEBHOOK_URL not configured');
    return;
  }

  try {
    // Fetch all live matches from proxy
    const liveMatchesUrl = `${PROXY_URL}/cricket/live`;
    const response = await fetch(liveMatchesUrl, {
      cf: { cacheTtl: 60 }, // Cache for 60 seconds on Cloudflare
    });

    if (!response.ok) {
      console.error(`Proxy returned ${response.status}: ${response.statusText}`);
      return;
    }

    const liveMatchesData = await response.json();

    if (!liveMatchesData.matches || liveMatchesData.matches.length === 0) {
      console.log('No live matches found');
      return;
    }

    // Filter matches by tournament name
    const filteredMatches = liveMatchesData.matches.filter(match => {
      const seriesName = match.series?.name || '';
      return seriesName.toUpperCase().includes(TOURNAMENT_FILTER.toUpperCase());
    });

    console.log(`Found ${filteredMatches.length} ${TOURNAMENT_FILTER} matches`);

    // Process each filtered match
    for (const match of filteredMatches) {
      await processMatch(match, KV, POKE_WEBHOOK, PROXY_URL);
    }
  } catch (error) {
    console.error('Worker error:', error.message);
  }
}

async function processMatch(matchSummary, KV, POKE_WEBHOOK, PROXY_URL) {
  const matchId = matchSummary.match_id;
  const matchUrl = `${PROXY_URL}/cricket/match/${matchId}`;

  try {
    // Fetch detailed match data from proxy
    const response = await fetch(matchUrl, {
      cf: { cacheTtl: 30 }, // Cache for 30 seconds on Cloudflare
    });

    if (!response.ok) {
      console.error(`Failed to fetch match ${matchId}: ${response.status}`);
      return;
    }

    const matchData = await response.json();

    if (!matchData || !matchData.match) {
      console.log(`No data for match ${matchId}`);
      return;
    }

    const match = matchData.match;
    const matchKey = `match:${matchId}`;

    // Get previous ball IDs we've already processed
    const previousBallIds = await KV.get(matchKey, 'json') || { processed_balls: [] };
    const processedBalls = new Set(previousBallIds.processed_balls || []);

    // Track new ball IDs for this run
    const newBallIds = new Set(processedBalls);

    // Detect and post new events
    await detectAndPostEvents(
      match,
      processedBalls,
      newBallIds,
      matchId,
      POKE_WEBHOOK
    );

    // Update KV with all processed ball IDs
    await KV.put(
      matchKey,
      JSON.stringify({
        processed_balls: Array.from(newBallIds),
        last_updated: new Date().toISOString(),
      }),
      { expirationTtl: 604800 } // 7 days
    );
  } catch (error) {
    console.error(`Error processing match ${matchId}:`, error.message);
  }
}

async function detectAndPostEvents(match, processedBalls, newBallIds, matchId, POKE_WEBHOOK) {
  const matchTitle = getMatchTitle(match);

  // Process all innings
  if (!match.innings || !Array.isArray(match.innings)) {
    return;
  }

  for (const inning of match.innings) {
    const teamName = inning.team?.name || 'Unknown';

    // Process all overs in this innings
    if (!inning.overs || !Array.isArray(inning.overs)) {
      continue;
    }

    for (const over of inning.overs) {
      const overNumber = over.number;

      // Process all deliveries in this over
      if (!over.deliveries || !Array.isArray(over.deliveries)) {
        continue;
      }

      for (const ball of over.deliveries) {
        // Create unique ball ID: "14.3" = over 14, ball 3
        const ballId = `${overNumber}.${(ball.sequence_number || 0) % 10}`;

        // Skip if we've already processed this ball
        if (processedBalls.has(ballId)) {
          continue;
        }

        // Mark as processed
        newBallIds.add(ballId);

        // Extract event details
        const currentScore = getScoreString(inning);
        const commentary = getCommentary(ball);

        // Check for wicket
        if (ball.wicket) {
          const wicketEvent = {
            match_id: matchId,
            match: matchTitle,
            type: 'wicket',
            over: overNumber,
            ball: ballId,
            team: teamName,
            batter: ball.batter?.name || 'Unknown',
            commentary: commentary,
            score: currentScore,
            timestamp: new Date().toISOString(),
          };
          await postToPokeWebhook(wicketEvent, POKE_WEBHOOK);
        }

        // Check for boundary (4 or 6)
        const runs = ball.runs?.runs || 0;
        if (runs >= 4) {
          const boundaryEvent = {
            match_id: matchId,
            match: matchTitle,
            type: runs === 4 ? '4' : '6',
            over: overNumber,
            ball: ballId,
            team: teamName,
            batter: ball.batter?.name || 'Unknown',
            runs: runs,
            commentary: commentary,
            score: currentScore,
            timestamp: new Date().toISOString(),
          };
          await postToPokeWebhook(boundaryEvent, POKE_WEBHOOK);
        }

        // Check for over completion
        if (over.complete && ball.sequence_number % 10 === 0) {
          const overCompleteEvent = {
            match_id: matchId,
            match: matchTitle,
            type: 'over_complete',
            over: overNumber,
            team: teamName,
            runs_in_over: getOverRuns(over),
            wickets_in_over: getOverWickets(over),
            score: currentScore,
            timestamp: new Date().toISOString(),
          };
          await postToPokeWebhook(overCompleteEvent, POKE_WEBHOOK);
        }
      }
    }
  }

  // Check for match status changes
  if (match.status_text) {
    const statusKey = `match_status:${matchId}`;
    const previousStatus = await KV.get(statusKey);

    if (previousStatus !== match.status_text) {
      const statusEvent = {
        match_id: matchId,
        match: matchTitle,
        type: 'match_status',
        status: match.status_text,
        commentary: match.status_text,
        timestamp: new Date().toISOString(),
      };
      await postToPokeWebhook(statusEvent, POKE_WEBHOOK);
      await KV.put(statusKey, match.status_text, { expirationTtl: 604800 });
    }
  }
}

function getCommentary(ball) {
  if (ball.commentary) {
    return ball.commentary;
  }

  // Build commentary from ball data
  const batter = ball.batter?.name || 'Unknown';
  const bowler = ball.bowler?.name || 'Unknown';
  const runs = ball.runs?.runs || 0;
  const extras = ball.runs?.extras || 0;

  let text = `${batter} to ${bowler}`;

  if (ball.wicket) {
    text += ` - ${ball.wicket.wicket_type || 'out'}`;
  } else if (runs === 4) {
    text += ' - FOUR!';
  } else if (runs === 6) {
    text += ' - SIX!';
  } else if (runs > 0) {
    text += ` - ${runs} runs`;
  } else if (extras > 0) {
    text += ` - ${extras} extras`;
  } else {
    text += ' - dot';
  }

  return text;
}

function getScoreString(inning) {
  if (!inning) return 'N/A';

  const team = inning.team?.name || 'Team';
  const runs = inning.runs || 0;
  const wickets = inning.wickets || 0;

  // Calculate overs from deliveries
  let totalDeliveries = 0;
  if (inning.overs && Array.isArray(inning.overs)) {
    for (const over of inning.overs) {
      if (over.deliveries) {
        totalDeliveries += over.deliveries.length;
      }
    }
  }

  const overs = Math.floor(totalDeliveries / 6);
  const balls = totalDeliveries % 6;

  return `${team} ${runs}/${wickets} (${overs}.${balls} ov)`;
}

function getMatchTitle(match) {
  if (match.match_title) {
    return match.match_title;
  }

  const team1 = match.teams?.[0]?.name || 'Team1';
  const team2 = match.teams?.[1]?.name || 'Team2';
  return `${team1} vs ${team2}`;
}

function getOverRuns(over) {
  if (!over.deliveries || !Array.isArray(over.deliveries)) {
    return 0;
  }

  let runs = 0;
  for (const ball of over.deliveries) {
    runs += (ball.runs?.runs || 0) + (ball.runs?.extras || 0);
  }
  return runs;
}

function getOverWickets(over) {
  if (!over.deliveries || !Array.isArray(over.deliveries)) {
    return 0;
  }

  return over.deliveries.filter(ball => ball.wicket).length;
}

async function postToPokeWebhook(event, webhookUrl) {
  try {
    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
    });

    if (!response.ok) {
      console.error(`Poke webhook failed: ${response.status} - ${response.statusText}`);
    } else {
      console.log(`Event posted: ${event.type} for ${event.match}`);
    }
  } catch (error) {
    console.error('Poke webhook error:', error.message);
  }
}
