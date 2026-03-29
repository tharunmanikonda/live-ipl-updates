#!/usr/bin/env python3
"""
Test script to verify webhook flow locally
Tests:
1. Register a webhook for a match
2. Trigger a test event
3. Monitor logs
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:5000"

def test_webhook_registration():
    """Test webhook registration"""
    print("\n=== Testing Webhook Registration ===")

    # Register a webhook
    webhook_data = {
        "match_id": "ipl2026_m2",
        "webhook_url": "https://webhook.site/your-unique-id"  # Replace with actual webhook.site URL
    }

    try:
        response = requests.post(f"{BASE_URL}/webhook/register", json=webhook_data)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 201
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_webhook_list():
    """List registered webhooks for a match"""
    print("\n=== Testing Webhook List ===")

    try:
        response = requests.get(f"{BASE_URL}/webhook/list/ipl2026_m2")
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Registered webhooks: {data['count']}")
        print(f"URLs: {json.dumps(data['webhooks'], indent=2)}")
        return data['count'] > 0
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_match_schedule():
    """Check match schedule"""
    print("\n=== Testing Match Schedule ===")

    try:
        response = requests.get(f"{BASE_URL}/schedule/list")
        print(f"Status: {response.status_code}")
        data = response.json()

        # Find match 2
        for match_id, match_data in data.get('matches', {}).items():
            if 'ipl2026_m2' in match_id or 'Match 2' in match_data.get('title', ''):
                print(f"\n📍 Match 2 Status:")
                print(f"   Title: {match_data.get('title')}")
                print(f"   Status: {match_data.get('status')}")
                print(f"   Start Time: {match_data.get('start_time')}")
                print(f"   Cricbuzz ID: {match_data.get('cricbuzz_id')}")
                if match_data.get('cricbuzz_id'):
                    print(f"   ✅ Cricbuzz ID fetched")
                return match_data.get('status') == 'live'

        print("❌ Match 2 not found in schedule")
        return False

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_debug_state():
    """Check internal state"""
    print("\n=== Testing Debug State ===")

    try:
        response = requests.get(f"{BASE_URL}/debug/state")
        print(f"Status: {response.status_code}")
        data = response.json()

        if 'match_state' in data:
            print(f"\n📊 Match States:")
            for match_id, state in data.get('match_state', {}).items():
                if 'ipl2026_m2' in match_id:
                    print(f"   Match: {match_id}")
                    print(f"   Last Timestamp: {state.get('last_timestamp')}")
                    print(f"   Balls Fetched: {len(state.get('balls', []))}")
                    print(f"   Match State: {state.get('match_state')}")

        if 'webhooks' in data:
            print(f"\n🔗 Registered Webhooks:")
            for match_id, urls in data.get('webhooks', {}).items():
                if 'ipl2026_m2' in match_id:
                    print(f"   Match: {match_id}")
                    print(f"   Count: {len(urls)}")
                    for url in urls:
                        print(f"   - {url}")

        return True
    except Exception as e:
        print(f"⚠️  Debug endpoint not available: {str(e)}")
        return False

def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("CRICKET WEBHOOK SYSTEM - LOCAL TEST")
    print("="*60)

    results = {
        'Register Webhook': test_webhook_registration(),
        'List Webhooks': test_webhook_list(),
        'Check Schedule': test_match_schedule(),
        'Debug State': test_debug_state(),
    }

    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name}: {status}")

    print("\n📝 Next Steps:")
    print("1. Replace 'webhook.site/your-unique-id' with actual webhook.site URL")
    print("2. Watch server logs for detailed debug output")
    print("3. Check webhook.site for incoming POST events")
    print("4. Monitor logs for: [POLL], [WEBHOOK], [AUTO-START] messages")

if __name__ == '__main__':
    run_all_tests()
