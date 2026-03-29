# Start Local Testing - 5 Minute Quick Start

## Your Webhook URL
```
https://webhook.site/dc9257f7-f338-4b3f-aa8b-8f2ed05eae84
```

## Step 1: Start Server (Terminal 1)
```bash
cd /Users/tharun/cricket-live-api/proxy-python
PORT=6666 python3 server.py
```

**Expected output:**
```
🏏 Cricket Python proxy starting on port 6666
[SCHEDULER] ✅ Smart polling initialized!
[SCHEDULER] Auto-start: Matches marked LIVE at scheduled start time (IST)
```

## Step 2: Bulk Load Matches (Terminal 2)
```bash
curl -s -X POST http://localhost:6666/schedule/bulk-load \
  -H "Content-Type: application/json" \
  --data-raw '{"pdf_path":"/Users/tharun/Downloads/IPL 2026 Schedule.pdf"}' | jq .
```

## Step 3: Register Webhook (Terminal 2)
```bash
curl -s -X POST http://localhost:6666/webhook/register \
  -H "Content-Type: application/json" \
  --data-raw '{"match_id":"ipl2026_m2","webhook_url":"https://webhook.site/dc9257f7-f338-4b3f-aa8b-8f2ed05eae84"}'
```

**Expected response:**
```json
{
  "status": "registered",
  "match_id": "ipl2026_m2",
  "webhook_url": "https://webhook.site/dc9257f7-f338-4b3f-aa8b-8f2ed05eae84",
  "total_webhooks": 1
}
```

## Step 4: Verify Setup (Terminal 2)
```bash
curl -s -X GET http://localhost:6666/debug/state | jq .
```

## Step 5: Check Webhook.site
Visit: https://webhook.site/dc9257f7-f338-4b3f-aa8b-8f2ed05eae84

Should see incoming POST events as they happen!

---

## Key Things to Watch in Server Logs (Terminal 1)

### At 8 PM IST (Match Start Time):
```
[AUTO-START] 🚀 Match ipl2026_m2 auto-started!
[AUTO-START] Cricbuzz ID: 149629
[AUTO-START] Teams: Mumbai vs Kolkata Knight Riders
```

### Every Minute During Match:
```
[POLL] Fetching data from timestamp: 1774792334 for match ipl2026_m2 (ID: 149629)
[POLL] Response status: 200
[POLL] Updating match ipl2026_m2 state: last_timestamp=1774792500, new_balls=12
```

### When Ball Event Detected:
```
[POLL] Detected 4 at 2.1 - Batsman Name
[WEBHOOK] Event triggered - match_id=ipl2026_m2, event_type=boundary, registered_webhooks=1
[WEBHOOK] ✅ Sent boundary to https://webhook.site/dc9257f7-f338-4b3f-aa8b-8f2ed05eae84
```

---

## Automated Test Script
```bash
cd /Users/tharun/cricket-live-api
./quick_test.sh 6666
```

---

## If Tests Pass
Push to GitHub and deploy to droplet:
```bash
cd /Users/tharun/cricket-live-api
git add -A
git commit -m "Fix timestamp bug and add detailed logging"
git push origin main

# On droplet:
cd ~/cricket-live-api
git pull origin main
# Restart server
```

---

## Critical Fixes Applied
✅ **Fixed timestamp bug** - Was using old timestamp instead of API response timestamp
✅ **Added API response logging** - See exactly what API returns
✅ **Added webhook event logging** - See when webhooks trigger
✅ **Added debug state endpoint** - Check internal state anytime

These changes ensure the timestamp updates properly, which was preventing subsequent polls from fetching new data.
