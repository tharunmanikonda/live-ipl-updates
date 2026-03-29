#!/bin/bash

# Quick test script using the user's webhook.site URL

WEBHOOK_URL="https://webhook.site/dc9257f7-f338-4b3f-aa8b-8f2ed05eae84"
API_PORT=${1:-6666}
API_BASE="http://localhost:${API_PORT}"

echo "========================================="
echo "Cricket Webhook System - Quick Test"
echo "========================================="
echo ""

# Step 1: Check health
echo "1️⃣  Checking API health..."
curl -s -X GET "$API_BASE/health" | jq .
echo ""

# Step 2: Register webhook
echo "2️⃣  Registering webhook for match ipl2026_m2..."
REGISTER_RESPONSE=$(curl -s -X POST "$API_BASE/webhook/register" \
  -H "Content-Type: application/json" \
  --data-raw "{\"match_id\":\"ipl2026_m2\",\"webhook_url\":\"$WEBHOOK_URL\"}")
echo "$REGISTER_RESPONSE" | jq .
echo ""

# Step 3: List webhooks
echo "3️⃣  Listing registered webhooks for match ipl2026_m2..."
curl -s -X GET "$API_BASE/webhook/list/ipl2026_m2" | jq .
echo ""

# Step 4: Check schedule
echo "4️⃣  Checking match 2 schedule..."
SCHEDULE=$(curl -s -X GET "$API_BASE/schedule/list" | jq '.matches[] | select(.title | contains("Match 2")) | {title, status, start_time, cricbuzz_id}')
echo "$SCHEDULE"
echo ""

# Step 5: Check debug state
echo "5️⃣  Checking internal state..."
curl -s -X GET "$API_BASE/debug/state" | jq '.match_state, .webhooks, .schedule_summary' 2>/dev/null || echo "Debug endpoint not ready yet"
echo ""

echo "========================================="
echo "✅ Test Complete!"
echo "========================================="
echo ""
echo "📊 Webhook URL: $WEBHOOK_URL"
echo "📊 Check webhook.site for incoming events"
echo ""
echo "📝 Key Things to Monitor:"
echo "  • Server logs for [POLL], [WEBHOOK], [AUTO-START] messages"
echo "  • Match status should be 'live' after 8 PM IST"
echo "  • Cricbuzz ID should be populated (e.g., 149629)"
echo "  • Events should POST to webhook.site"
echo ""
echo "⏱️  Testing now..."
sleep 5
echo ""
echo "📱 Final state check:"
curl -s -X GET "$API_BASE/debug/state" | jq . 2>/dev/null || echo "State check failed"
