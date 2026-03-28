# Cricket Live Score — Poke Integration (IPL Alerts)

A **serverless event pusher** that monitors ESPNcricinfo for live cricket matches (IPL, T20WC, etc.) and POSTs real-time events (balls, wickets, boundaries) to your Poke recipe webhook. Poke then delivers notifications to all subscribers via iMessage, WhatsApp, or other channels.

## Features

- ✅ **Zero Backend** — Pure Cloudflare Workers + Poke automation
- ✅ **Real-time Events** — Updates every 1 minute via cron trigger
- ✅ **Tournament Filtering** — Configurable filter (IPL, T20WC, ODI, etc.)
- ✅ **Rich Notifications** — Full context: teams, score, over, commentary
- ✅ **Ball-by-Ball Tracking** — Deduplication using ball IDs (e.g., "14.3")
- ✅ **Multi-User via Poke** — Poke manages subscriptions, you manage events
- ✅ **Free Tier Friendly** — Completes within Workers + KV free limits

## Architecture

```
Cloudflare Worker (every 1 min)
  ↓ Filter live matches by tournament
  ↓ Fetch ESPNcricinfo ball-by-ball data
  ↓ Compare ball IDs with KV state
  ↓ Detect new events (wickets, boundaries, overs)
  ↓ Extract rich context (score, commentary)
  ↓ POST to Poke Webhook
  ↓
Poke Recipe (webhook trigger)
  ↓ Receives event
  ↓ Formats message
  ↓ Delivers to all subscribers (iMessage, WhatsApp, etc.)
```

## Project Structure

```
cricket-live-api/
├── worker/
│   ├── index.js        # Event detector + Poke poster
│   └── wrangler.toml   # Cloudflare config + tournament filter
└── README.md
```

## Setup Instructions

### Step 1: Create Poke Recipe

1. Go to [Poke.delivery](https://poke.delivery) (or your Poke instance)
2. Create a new recipe:
   - **Name**: "IPL Live Alerts" (or your tournament name)
   - **Trigger**: Webhook
   - **Action**: Send iMessage/WhatsApp notification
3. Poke generates a webhook URL: `https://poke.delivery/webhooks/12345abcde`
4. Copy this URL — you'll need it in the next step

### Step 2: Install Cloudflare Worker

```bash
npm install -g wrangler
cd cricket-live-api/worker
```

### Step 3: Authenticate

```bash
wrangler login
```

### Step 4: Create KV Namespace

```bash
wrangler kv:namespace create CRICKET_STATE
```

Output:
```
Created namespace with id: 12345abc-67890def-xyz
```

### Step 5: Update wrangler.toml

Replace `YOUR_KV_NAMESPACE_ID` with the ID from Step 4:

```toml
[[kv_namespaces]]
binding = "CRICKET_STATE"
id = "12345abc-67890def-xyz"  # ← Your ID
```

### Step 6: Set Poke Webhook URL

```bash
wrangler secret put POKE_WEBHOOK_URL
```

Paste your Poke webhook URL (from Step 1):
```
https://poke.delivery/webhooks/12345abcde
```

### Step 7: Configure Tournament Filter (Optional)

Edit `wrangler.toml`:

```toml
[env.production]
vars = {
  TOURNAMENT_FILTER = "IPL"  # Change to "T20WC", "ODI", etc.
}
```

### Step 8: Deploy

```bash
wrangler deploy
```

Success:
```
✓ Deployed cricket-live-worker to https://cricket-live-worker.YOUR_SUBDOMAIN.workers.dev
```

## How It Works

### 1. Filter by Tournament

Worker fetches live matches and filters by series name:
```javascript
const filteredMatches = liveMatches.filter(m =>
  m.series.name.includes('IPL')
);
```

**Change tournament without code:**
```bash
# Only T20 World Cup
wrangler secret put TOURNAMENT_FILTER --path production
T20WC

# Only ODI matches
TOURNAMENT_FILTER=ODI wrangler deploy
```

### 2. Track Ball-by-Ball

For each match, store processed ball IDs in KV:
```
match:1415671 → {
  processed_balls: ["0.1", "0.2", "0.3", "0.4", ..., "14.3"],
  last_updated: "2026-03-28T10:34:00Z"
}
```

When worker runs next minute:
- Fetch new match data
- Compare ball IDs
- Only post NEW balls (14.4, 14.5, 14.6 if they're new)
- Update KV

**Ball ID format**: `over.ball` (e.g., "14.3" = over 14, ball 3)
- Avoids duplicates even if two balls recorded in same second
- Cleaner than timestamps

### 3. Detect Events

For each new ball:
- **Wicket**: Check `ball.wicket` flag
- **Boundary**: Check if `ball.runs.runs >= 4`
- **Over complete**: Check if ball completes the over (6th ball)
- **Match status**: Track when match starts/ends

### 4. Build Rich Payload

Each event includes full context:

```json
{
  "match_id": "1415671",
  "match": "RCB vs CSK",
  "type": "wicket",
  "over": 14,
  "ball": "14.3",
  "team": "RCB",
  "batter": "Virat Kohli",
  "commentary": "Virat Kohli to Hazlewood - caught!",
  "score": "RCB 156/3 (14.3 ov)",
  "timestamp": "2026-03-28T10:34:00Z"
}
```

### 5. Post to Poke

Worker POSTs each event to your Poke webhook. Poke receives it and:
- Formats a readable notification
- Delivers to all subscribers

## Webhook Payload Format

### Event Types

| Type | When | Example |
|------|------|---------|
| `wicket` | Batsman out | Kohli caught by Hazlewood |
| `4` | Boundary (4 runs) | Boundary! Kohli smashes it |
| `6` | Boundary (6 runs) | SIX! Over the boundary |
| `over_complete` | Over ends | Over 14 completed: 8 runs, 1 wicket |
| `match_status` | Match starts/ends | Match started / Match ended |

### Full Payload Structure

```json
{
  "match_id": "1415671",
  "match": "RCB vs CSK",
  "type": "wicket",
  "over": 14,
  "ball": "14.3",
  "team": "RCB",
  "batter": "Virat Kohli",
  "commentary": "Virat Kohli to Hazlewood - caught!",
  "score": "RCB 156/3 (14.3 ov)",
  "timestamp": "2026-03-28T10:34:00Z"
}
```

For boundaries:
```json
{
  "match_id": "1415671",
  "match": "RCB vs CSK",
  "type": "4",
  "over": 14,
  "ball": "14.1",
  "team": "RCB",
  "batter": "Virat Kohli",
  "runs": 4,
  "commentary": "Virat Kohli to Hazlewood - FOUR!",
  "score": "RCB 156/2 (14.1 ov)",
  "timestamp": "2026-03-28T10:34:00Z"
}
```

## Using in Your Poke Recipe

When Poke receives the webhook, format the notification:

```javascript
// In your Poke recipe action (pseudo-code)
const event = payload;

if (event.type === 'wicket') {
  message = `🏏 WICKET!\n${event.batter} is out in ${event.match}!\nScore: ${event.score}`;
} else if (event.type === '6') {
  message = `💥 SIX!\n${event.batter} hits a 6!\n${event.match}: ${event.score}`;
} else if (event.type === '4') {
  message = `🎯 FOUR!\n${event.batter} hits a boundary!\n${event.match}: ${event.score}`;
} else if (event.type === 'over_complete') {
  message = `✅ Over ${event.over} complete\n${event.team}: ${event.score}`;
}

sendMessage(message);
```

## Troubleshooting

### No events arriving at Poke?

1. **Check Poke webhook is reachable:**
   ```bash
   curl -X POST https://poke.delivery/webhooks/YOUR_WEBHOOK_ID \
     -H "Content-Type: application/json" \
     -d '{"test": "data"}'
   ```

2. **View worker logs:**
   ```bash
   wrangler tail --follow
   ```

3. **Check for live matches:**
   ```bash
   curl https://www.espncricinfo.com/matches/engine/match/live.json | jq '.matches[] | select(.series.name | contains("IPL"))'
   ```

4. **Verify KV namespace is bound:**
   ```bash
   wrangler kv:key list --namespace-id=YOUR_KV_ID
   ```

### Events are duplicating?

Ball IDs should prevent this. If happening:
- Check KV is being updated: `wrangler tail --follow`
- Manually clear KV: `wrangler kv:key delete --namespace-id=YOUR_KV_ID match:MATCH_ID`

### Tournament filter not working?

1. Check filter string matches series name:
   ```bash
   curl https://www.espncricinfo.com/matches/engine/match/live.json | jq '.matches[].series.name'
   ```

2. Verify wrangler.toml has correct filter:
   ```toml
   [env.production]
   vars = { TOURNAMENT_FILTER = "IPL" }
   ```

3. Redeploy:
   ```bash
   wrangler deploy
   ```

## Performance & Costs

### Execution Time

Per minute run:
- Fetch live matches: ~300ms
- Fetch 3-5 active matches: ~1-2s
- Process & detect events: ~500ms
- Post to Poke: ~1s
- **Total: 3-4 seconds** ✅ (well under 30s limit)

### Free Tier Usage

| Resource | Limit | Usage/month | Cost |
|----------|-------|------------|------|
| Worker requests | 100k/day | ~43k | **$0** |
| KV reads | 1M/day | ~43k | **$0** |
| KV writes | 100k/day | ~43k | **$0** |
| KV storage | 1GB | <10MB | **$0** |
| Cron triggers | Unlimited | 43.2k | **$0** |
| **Total** | - | - | **$0/month** |

## Future Enhancements

For v2 (multi-user per-team filtering):
- [ ] Store match→user subscription mapping in KV
- [ ] Route each event to specific user webhooks
- [ ] Add user preferences (only wickets, only my team, etc.)

For now, **Poke manages subscriptions** and you manage events. One worker → One Poke recipe → Many subscribers.

## Development

To test locally:

```bash
wrangler dev
```

Then manually trigger (requires Pro account) or add an HTTP endpoint:

```javascript
export default {
  async fetch(request) {
    if (new URL(request.url).pathname === '/test') {
      return handleScheduled({}, env);
    }
    return new Response('OK');
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil(handleScheduled(event, env));
  },
};
```

Test: `curl http://localhost:8787/test`

## Deployment Checklist

- [ ] Poke recipe created and webhook URL copied
- [ ] Cloudflare account created
- [ ] wrangler installed and authenticated
- [ ] KV namespace created and ID added to wrangler.toml
- [ ] POKE_WEBHOOK_URL secret set
- [ ] TOURNAMENT_FILTER configured (if not IPL)
- [ ] Deployed: `wrangler deploy`
- [ ] Live matches exist for your tournament
- [ ] Events arriving in Poke (check webhook logs)

## License

MIT

## Support

- **Cloudflare Workers**: [Docs](https://developers.cloudflare.com/workers/)
- **ESPNcricinfo API**: Test at `https://www.espncricinfo.com/matches/engine/match/live.json`
- **Poke**: Visit [Poke.delivery](https://poke.delivery)
