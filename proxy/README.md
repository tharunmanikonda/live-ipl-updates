# Cricket Proxy Server

A lightweight proxy server that fetches cricket data from ESPNcricinfo and serves it via HTTP. This bypasses IP-based blocking by using residential IPs instead of Cloudflare Workers.

## Features

- ✅ Proxies ESPNcricinfo API requests
- ✅ Caches responses for 60 seconds (reduces load)
- ✅ Human-like headers (bypasses basic bot detection)
- ✅ Health check endpoint
- ✅ Lightweight (~2MB)
- ✅ Free deployment on Railway

## Local Development

```bash
npm install
npm start
```

Server runs on `http://localhost:3000`

### Endpoints

- **Health Check**: `GET http://localhost:3000/health`
- **Live Matches**: `GET http://localhost:3000/cricket/live`
- **Match Details**: `GET http://localhost:3000/cricket/match/{matchId}`

### Test Locally

```bash
# Check health
curl http://localhost:3000/health

# Get live matches
curl http://localhost:3000/cricket/live | jq '.'

# Get specific match
curl http://localhost:3000/cricket/match/1415671 | jq '.'
```

## Deploy to Railway (Free)

### Step 1: Create Railway Account

Go to https://railway.app and sign up with GitHub

### Step 2: Create New Project

1. Click "New Project"
2. Select "Deploy from GitHub"
3. Connect your GitHub account
4. Select your `cricket-live-api` repo
5. Select the `proxy` directory as the root

### Step 3: Configure Environment

Railway auto-detects Node.js. It will:
- Install dependencies from `package.json`
- Run `npm start`
- Assign a public URL like: `https://cricket-proxy-production.up.railway.app`

### Step 4: Deploy

Click "Deploy" and wait for the green checkmark (~2 minutes)

### Step 5: Get Your Proxy URL

Once deployed, you'll see a URL like:
```
https://cricket-proxy-production.up.railway.app
```

Use this in your Cloudflare Worker!

## Update Cloudflare Worker

In your Worker (`worker/index.js`), change:

```javascript
// OLD:
const liveMatchesUrl = 'https://www.espncricinfo.com/matches/engine/match/live.json';

// NEW:
const liveMatchesUrl = 'https://YOUR-RAILWAY-URL/cricket/live';
```

And:

```javascript
// OLD:
const matchUrl = `https://www.espncricinfo.com/matches/engine/match/${matchId}/live.json`;

// NEW:
const matchUrl = `https://YOUR-RAILWAY-URL/cricket/match/${matchId}`;
```

Then redeploy your Worker:
```bash
wrangler deploy
```

## How It Works

```
Cloudflare Worker
    ↓ HTTP GET
Your Railway Proxy
    ↓ HTTP GET (with human headers)
ESPNcricinfo
    ↓ JSON response
Proxy (caches for 60s)
    ↓ Returns JSON
Cloudflare Worker (processes, detects events)
    ↓ HTTP POST
Poke Webhook
```

## Caching

- Responses cached for **60 seconds**
- Each request checks cache first
- Reduces load on ESPNcricinfo
- Keeps your polling fast

## Logs

View logs in Railway dashboard:
- Click your project
- Click "Deployments" tab
- Click "View Logs"
- See real-time proxy logs

Example logs:
```
[FETCHING] Live matches from ESPNcricinfo
[CACHE HIT] Match 1415671
[ERROR] ESPNcricinfo returned 403
```

## Troubleshooting

### Proxy returns 403 Forbidden

If the proxy still gets blocked:
1. Check Railway logs for the exact error
2. Try upgrading to a paid proxy service (Bright Data, Oxylabs)
3. Contact ESPNcricinfo for API access

### Proxy times out

- ESPNcricinfo might be slow
- Check Railway logs
- Increase timeout in `server.js` if needed

### Worker doesn't connect to proxy

1. Verify proxy URL in worker code
2. Check proxy is deployed and running (Railway dashboard)
3. Test proxy URL manually: `curl https://YOUR-RAILWAY-URL/health`

## Cost

- **Railway free tier**: 500 hours/month
- Your proxy runs 24/7: ~720 hours/month
- **Cost: $5/month** (or use free tier with auto-sleep)

*Note: Free tier includes auto-sleep after 24h inactivity. Upgrade to paid ($5/month) for always-on.*

## Next Steps

1. Deploy proxy to Railway
2. Get the Railway URL
3. Update Cloudflare Worker with new proxy URL
4. Redeploy Worker
5. Monitor logs to verify it's working
6. Check Poke notifications for cricket events!
