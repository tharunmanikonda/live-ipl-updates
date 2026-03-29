# Local Testing Guide - Cricket Webhook System

## Setup

### 1. Start the Server

```bash
cd /Users/tharun/cricket-live-api/proxy-python
python3 server.py
```

Server runs on port 6666 (or set PORT env var):
```bash
PORT=6666 python3 server.py
```

### 2. Bulk Load Matches (First Time Only)

```bash
curl -s -X POST http://localhost:6666/schedule/bulk-load \
  -H "Content-Type: application/json" \
  --data-raw '{"pdf_path":"/Users/tharun/Downloads/IPL 2026 Schedule.pdf"}'
```

**Expected Response:**
```json
{
  "status": "loaded",
  "total_matches": 70,
  "sample_matches": [...]
}
```

---

## Testing Flow

### Step 1: Register Your Webhook

```bash
curl -s -X POST http://localhost:6666/webhook/register \
  -H "Content-Type: application/json" \
  --data-raw '{"match_id":"ipl2026_m2","webhook_url":"https://webhook.site/dc9257f7-f338-4b3f-aa8b-8f2ed05eae84"}'
```

**Expected Response:**
```json
{
  "status": "registered",
  "match_id": "ipl2026_m2",
  "webhook_url": "https://webhook.site/dc9257f7-f338-4b3f-aa8b-8f2ed05eae84",
  "total_webhooks": 1
}
```

### Step 2: Check Registered Webhooks

```bash
curl -s -X GET http://localhost:6666/webhook/list/ipl2026_m2 | jq .
```

**Expected Response:**
```json
{
  "match_id": "ipl2026_m2",
  "webhooks": [
    "https://webhook.site/dc9257f7-f338-4b3f-aa8b-8f2ed05eae84"
  ],
  "count": 1
}
```

### Step 3: Check Match Schedule

```bash
curl -s -X GET http://localhost:6666/schedule/list | jq '.matches | .["ipl2026_m2"]'
```

**Expected Response (when not yet live):**
```json
{
  "title": "Match 2: Mumbai Indians vs Kolkata Knight Riders",
  "teams": "MI vs KKR",
  "status": "scheduled",
  "start_time": "2026-03-29 20:00 IST",
  "venue": "Arun Jaitley Stadium, Delhi",
  "created_at": "2026-03-29T14:00:00Z"
}
```

**After 8 PM IST, status changes to "live" with new fields:**
```json
{
  "title": "Match 2: Mumbai Indians vs Kolkata Knight Riders",
  "teams": "MI vs KKR",
  "status": "live",
  "start_time": "2026-03-29 20:00 IST",
  "venue": "Arun Jaitley Stadium, Delhi",
  "created_at": "2026-03-29T14:00:00Z",
  "cricbuzz_id": 149629,
  "match_title": "Mumbai vs Kolkata Knight Riders",
  "team1": "Mumbai",
  "team2": "Kolkata",
  "match_url": "https://www.cricbuzz.com/live-cricket-stream/149629/...",
  "commentary_api_url": "https://www.cricbuzz.com/api/mcenter/commentary-pagination/149629/...",
  "found_at": "2026-03-29T14:30:00Z"
}
```

### Step 4: Check Internal State

```bash
curl -s -X GET http://localhost:6666/debug/state | jq .
```

**Shows:**
- `match_state`: Last timestamp, ball count, match state for each match
- `webhooks`: Registered webhooks per match
- `schedule_summary`: Title, status, start time, Cricbuzz ID per match

---

## Event Flow & Logs to Watch

### Timeline

**Before 8 PM IST:**
- Match status: `scheduled`
- Polling: OFF
- Logs: None (waiting for start time)

**At 8 PM IST:**
- Auto-start triggers `auto_start_matches()`
- Logs:
  ```
  [AUTO-START] 🚀 Match ipl2026_m2 auto-started!
  [AUTO-START] Cricbuzz ID: 149629
  [AUTO-START] Teams: Mumbai vs Kolkata Knight Riders
  [AUTO-START] All match info stored in schedule ✅
  ```
- Match status: `live`
- Polling: ON (every 1 minute)

**During Match (Every Minute):**
- Logs:
  ```
  [POLL] Fetching data from timestamp: 0 for match ipl2026_m2 (ID: 149629)
  [POLL] Fetching URL: https://www.cricbuzz.com/api/mcenter/commentary-pagination/149629/2/0
  [POLL] Response status: 200
  [POLL] API response type: <class 'list'>, length: 45
  [POLL] Latest item keys: ['timestamp', 'commType', ...]
  [POLL] New timestamp from API: 1774792334, max so far: 1774792334
  [POLL] Updating match ipl2026_m2 state: last_timestamp=1774792334, new_balls=12, total_balls=12
  ```

**When Ball Event Detected:**
- Logs:
  ```
  [WEBHOOK] Event triggered - match_id=ipl2026_m2, event_type=boundary, registered_webhooks=1
  [WEBHOOK] ✅ Sent boundary to https://webhook.site/dc9257f7-f338-4b3f-aa8b-8f2ed05eae84
  ```

**At 12 AM IST or Match Ends:**
- Logs:
  ```
  [POLL] ⏰ Past 12 AM IST cutoff for match ipl2026_m2 - stopping polling
  ```
- Match status: `completed`
- Polling: OFF

---

## Troubleshooting

### Problem: Status stays "scheduled" after 8 PM IST

Check logs for:
```
[AUTO-START] Checking for matches that should start...
```

If this is missing, APScheduler might not have started. Check:
```bash
curl -s -X GET http://localhost:6666/health
```

### Problem: No webhooks triggered

Check:
1. **Are webhooks registered?**
   ```bash
   curl -s -X GET http://localhost:6666/webhook/list/ipl2026_m2
   ```

2. **Is the match status "live"?**
   ```bash
   curl -s -X GET http://localhost:6666/schedule/list | jq '.matches.ipl2026_m2.status'
   ```

3. **What's the last_timestamp?**
   ```bash
   curl -s -X GET http://localhost:6666/debug/state | jq '.match_state.ipl2026_m2'
   ```

4. **Check server logs** for:
   - `[POLL]` messages (polling running?)
   - `[WEBHOOK] Event triggered` (events detected?)
   - `[WEBHOOK] ✅ Sent` (webhook delivery?)

### Problem: Timestamp stuck at 0

This indicates the API response isn't being processed. Check logs for:
- `[POLL] API response type: <class 'list'>, length: X` - is length > 0?
- `[POLL] Latest item keys:` - does it have 'timestamp' field?

### Problem: Webhook.site not receiving events

1. Verify webhook URL is correct:
   ```bash
   curl -s -X GET http://localhost:6666/webhook/list/ipl2026_m2 | jq '.webhooks[0]'
   ```

2. Test POST directly:
   ```bash
   curl -X POST "https://webhook.site/dc9257f7-f338-4b3f-aa8b-8f2ed05eae84" \
     -H "Content-Type: application/json" \
     -d '{"test":"event"}'
   ```

---

## Quick Test Script

Run the automated test:
```bash
cd /Users/tharun/cricket-live-api
./quick_test.sh 6666
```

This will:
1. Check API health
2. Register webhook
3. List webhooks
4. Check schedule
5. Check internal state

---

## What Should Happen?

### Best Case Scenario
```
✅ At 8 PM IST:
   - Match auto-marked as LIVE
   - Cricbuzz ID fetched (149629)
   - Polling starts every 1 minute

✅ During match:
   - API returns commentary data
   - Timestamp updates each poll
   - Events detected and webhook triggered
   - Events appear on webhook.site

✅ At 12 AM IST:
   - Polling auto-stops
   - Match marked as COMPLETED
```

### Key Metrics to Track
- `last_timestamp`: Should increase every poll (e.g., 0 → 1774792334 → 1774792500 → ...)
- `balls_count`: Should increase as new commentary comes in
- Webhook responses: Check webhook.site for incoming POSTs

---

## Log Patterns to Look For

✅ **Good Pattern:**
```
[POLL] Fetching data from timestamp: 1774792334 for match ipl2026_m2 (ID: 149629)
[POLL] Response status: 200
[POLL] API response type: <class 'list'>, length: 15
[POLL] Updating match ipl2026_m2 state: last_timestamp=1774792500, new_balls=3, total_balls=18
[WEBHOOK] Event triggered - match_id=ipl2026_m2, event_type=boundary, registered_webhooks=1
[WEBHOOK] ✅ Sent boundary to https://webhook.site/...
```

❌ **Bad Pattern:**
```
[POLL] Fetching data from timestamp: 0 for match ipl2026_m2 (ID: 149629)
[POLL] Response status: 200
[POLL] API response type: <class 'list'>, length: 0  ← Empty response
[POLL] Updating match ipl2026_m2 state: last_timestamp=0, new_balls=0, total_balls=0
```

---

## Next Steps if Tests Pass

1. Push to GitHub
2. Pull on DigitalOcean droplet
3. Restart server on droplet
4. Verify polling works on real match
