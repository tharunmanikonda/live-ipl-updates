# Complete Deployment Guide: Cricket Live Score System

This guide walks you through deploying the entire system: Proxy + Cloudflare Worker + Poke Integration.

## Architecture

```
Railway Proxy (residential IP)
    ↓ Fetches ESPNcricinfo
    ↓
Cloudflare Worker (every 1 minute)
    ↓ Calls proxy, detects events
    ↓
Poke Webhook
    ↓
Your notifications (iMessage/WhatsApp)
```

---

## Prerequisites

- Cloudflare account (already have ✅)
- Railway account (free) — create at https://railway.app
- Your Poke webhook URL (already have ✅)
- Git repo on GitHub (for Railway auto-deploy)

---

## Step 1: Deploy Proxy to Railway

### Option A: GitHub Auto-Deploy (Recommended)

1. **Push your code to GitHub**
   ```bash
   cd /Users/tharun/cricket-live-api
   git init
   git add .
   git commit -m "Initial cricket proxy + worker setup"
   git remote add origin https://github.com/YOUR_USERNAME/cricket-live-api.git
   git push -u origin main
   ```

2. **Go to https://railway.app**
   - Click "New Project"
   - Select "Deploy from GitHub"
   - Select your `cricket-live-api` repository
   - Railway auto-detects Node.js
   - Click "Deploy"

3. **Wait for deployment** (~2 minutes)
   - You'll see a green checkmark
   - Railway assigns a URL: `https://cricket-proxy-production.up.railway.app`

### Option B: Manual Deployment

If you don't have GitHub:

1. **Install Railway CLI**
   ```bash
   npm install -g @railway/cli
   ```

2. **Login and Deploy**
   ```bash
   cd /Users/tharun/cricket-live-api/proxy
   railway login
   railway init
   railway up
   ```

3. **Get Proxy URL**
   ```bash
   railway open
   ```
   Railway shows your public URL

---

## Step 2: Test Proxy

Before updating the Worker, verify the proxy works:

```bash
# Replace with your Railway URL
PROXY_URL="https://cricket-proxy-production.up.railway.app"

# Test health
curl $PROXY_URL/health

# Test live matches
curl $PROXY_URL/cricket/live | jq '.matches | length'

# Expected output: Number of live matches (or empty array if no matches)
```

**If you get errors:**
- 403 Forbidden → Proxy blocked too (rare, try again in 5 min)
- Timeout → Railway server might be sleeping (wait 30 sec, try again)
- Connection refused → Deployment still in progress

---

## Step 3: Update Cloudflare Worker

### Update wrangler.toml

Edit `worker/wrangler.toml` and replace `PROXY_URL`:

```toml
vars = {
  TOURNAMENT_FILTER = "IPL",
  PROXY_URL = "https://cricket-proxy-production.up.railway.app"
}
```

**Replace `https://cricket-proxy-production.up.railway.app` with YOUR Railway URL**

### Redeploy Worker

```bash
cd /Users/tharun/cricket-live-api/worker
wrangler deploy
```

Output:
```
Uploaded cricket-live-worker (5.72 sec)
Current Version ID: [new-version-id]
```

---

## Step 4: Monitor & Test

### View Worker Logs

```bash
wrangler tail --follow
```

You should see:
```
✓ Found 2 IPL matches
✓ Event posted: wicket for RCB vs CSK
✓ Event posted: 6 for RCB vs CSK
```

### View Proxy Logs

Go to https://railway.app:
1. Click your project
2. Click "Deployments"
3. Click your deployment
4. Click "View Logs"

You should see:
```
[FETCHING] Live matches from ESPNcricinfo
[CACHE HIT] Match 1415671
[FETCHING] Match 1415671 from ESPNcricinfo
```

### Check Poke Notifications

When there's an IPL match live:
1. Check your iMessage/WhatsApp
2. Should see cricket event notifications
3. Each wicket/boundary within ~1 minute

---

## Step 5: Troubleshooting

### Worker says "Proxy returned 403"

**Problem:** Proxy is also getting blocked

**Solutions:**
1. Wait 5 minutes (ESPNcricinfo might temporarily unblock)
2. Try from a different Railway region (Railway settings)
3. Upgrade to paid proxy service (Bright Data, $15/month)

### No events showing up in Poke

**Check:**
1. Is there a live IPL match? (Check ESPN website)
2. Are Worker logs showing "Event posted"?
3. Is Poke webhook URL correct?
4. Check Poke logs/webhook history

### Proxy keeps timing out

**Solutions:**
1. Increase timeout in `proxy/server.js`:
   ```javascript
   timeout: 15000, // was 10000
   ```
2. Redeploy proxy
3. Check Railway logs for slow responses

### Railway free tier sleeping

**Problem:** Proxy goes to sleep after 24h inactivity

**Solution:** Upgrade Railway to paid ($5/month)
- Click project → Settings → Plan
- Upgrade to "Pro"

---

## Monitoring Checklist

After deployment, verify:

- [ ] Proxy returns 200 at `/health`
- [ ] Worker logs show "Found X IPL matches"
- [ ] Worker logs show "Event posted" for events
- [ ] Poke receives webhooks (check logs)
- [ ] Notifications arrive on iMessage/WhatsApp
- [ ] Cron trigger running every 1 minute

---

## Cost Breakdown

| Component | Cost | Notes |
|-----------|------|-------|
| Cloudflare Worker | FREE | Included in free tier |
| Workers KV | FREE | 1M reads/day free |
| Railway Proxy | $5/month | For always-on (optional: free with auto-sleep) |
| Poke Integration | FREE | Just routing webhooks |
| **Total** | **$5/month** | (or FREE if Railway auto-sleep OK) |

---

## Next Steps

1. ✅ Deploy proxy to Railway
2. ✅ Update Worker with proxy URL
3. ✅ Verify logs in both systems
4. ✅ Check Poke notifications
5. 🎉 Done! You're live

---

## Need Help?

**Worker Issues:**
```bash
# View real-time logs
wrangler tail --follow
```

**Proxy Issues:**
- Check Railway dashboard for deployment status
- View proxy logs in Railway UI
- Restart deployment if stuck

**Poke Issues:**
- Check Poke webhook logs
- Verify webhook URL in `wrangler.toml`
- Test webhook manually:
  ```bash
  curl -X POST YOUR_POKE_URL \
    -H "Content-Type: application/json" \
    -d '{"test": "event"}'
  ```

---

## Celebrate! 🏏

Your cricket live score system is now:
- ✅ Running on Cloudflare (global, fast)
- ✅ Pulling from ESPNcricinfo via proxy (bypassing blocks)
- ✅ Detecting events in real-time (every 1 minute)
- ✅ Sending notifications via Poke (iMessage/WhatsApp)

Enjoy live cricket alerts! 🎉
