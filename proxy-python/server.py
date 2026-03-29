from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import logging
import json
from apscheduler.schedulers.background import BackgroundScheduler
from threading import Lock

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_with_playwright(url, wait_selector=None, scroll_to_bottom=False):
    """Placeholder for Playwright support - requires async event loop management"""
    logger.info('[DEBUG] Playwright fetch requested but using fallback method')
    return None

# Webhook storage (in-memory for now, use database in production)
webhooks = {}  # {match_id: [webhook_urls]}

# State tracking for live matches (to detect new events)
match_state = {}  # {match_id: {balls: [...], last_over: X, last_innings: X, last_timestamp: X}}
state_lock = Lock()

# Headers to mimic browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# Cache for 60 seconds
cache = {}
CACHE_TTL = 60

def get_from_cache(key):
    if key in cache:
        if datetime.now().timestamp() - cache[key]['timestamp'] < CACHE_TTL:
            return cache[key]['data']
    return None

def set_cache(key, data):
    cache[key] = {
        'data': data,
        'timestamp': datetime.now().timestamp()
    }

def check_match_completion_from_api(match_id):
    """
    Check if match is complete from API response
    Returns True if match is complete, False otherwise
    """
    try:
        url = f'https://www.cricbuzz.com/api/mcenter/comm/{match_id}'
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            header = data.get('matchHeader', {})

            # Check if match is marked as complete
            if header.get('complete') == True:
                logger.info(f'[API] Match {match_id} is COMPLETE (from API)')
                return True

            # Check state field
            state = header.get('state', '').lower()
            if state == 'complete':
                logger.info(f'[API] Match {match_id} state is COMPLETE (from API)')
                return True

        return False
    except Exception as e:
        logger.debug(f'[API] Error checking completion: {str(e)}')
        return False

def should_stop_polling(match_id):
    """
    Check if polling should stop for this match
    1. Check API if match is complete
    2. Fallback to 12 AM cutoff
    """
    # Primary: Check API
    if check_match_completion_from_api(match_id):
        return True

    # Fallback: 12 AM cutoff
    try:
        # Get match start time from schedule
        with state_lock:
            if match_id not in matches_schedule:
                return False

            start_time_str = matches_schedule[match_id].get('start_time', '')

        if not start_time_str:
            return False

        # Parse start time (format: "2026-03-29 19:00" IST)
        start_dt = datetime.fromisoformat(start_time_str.split(' IST')[0])

        # If current time is past next day 12:00 AM, stop polling
        current_time = datetime.now()
        next_midnight = start_dt.replace(hour=0, minute=0, second=0) + timedelta(days=1)

        if current_time >= next_midnight:
            logger.info(f'[POLL] ⏰ Past 12 AM cutoff for match {match_id} - stopping polling')
            return True

        return False
    except Exception as e:
        logger.debug(f'[POLL] Error checking time cutoff: {str(e)}')
        return False

def send_webhook_event(match_id, event_type, event_data):
    """Send webhook event to all subscribed webhooks for a match"""
    match_webhooks = webhooks.get(match_id, [])
    if not match_webhooks:
        return 0, 0

    payload = {
        'match_id': match_id,
        'event_type': event_type,
        'event_data': event_data,
        'timestamp': datetime.now().isoformat()
    }

    sent = 0
    failed = 0
    for webhook_url in match_webhooks:
        try:
            response = requests.post(webhook_url, json=payload, timeout=5)
            if response.status_code in [200, 201, 202]:
                sent += 1
                logger.info(f'[WEBHOOK] Sent {event_type} to {webhook_url}')
            else:
                failed += 1
                logger.warning(f'[WEBHOOK] Failed to send to {webhook_url}: {response.status_code}')
        except Exception as e:
            failed += 1
            logger.debug(f'[WEBHOOK] Error sending to {webhook_url}: {str(e)}')

    return sent, failed

# Track polling state
polling_state = {
    'active_matches': set(),  # Currently live matches
    'polling_mode': 'light',  # 'light' or 'intensive'
    'last_check': None
}

# Match schedule document - tracks when matches happen
matches_schedule = {
    # Format: match_id: {title, start_time, status, created_at}
    # Status: 'scheduled', 'live', 'completed', 'cancelled'
}

def poll_live_matches():
    """Background job: Smart polling - only intensive when matches are live"""
    try:
        logger.info('[POLL] Checking for live matches...')

        # Get live matches
        response = requests.get('https://www.cricbuzz.com/cricket-match/live-scores', headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        match_links = soup.find_all('a', class_=re.compile(r'block\s+mb-3'))
        live_matches = {}

        for match_link in match_links:
            href = match_link.get('href', '')
            if not href or '/live-cricket-scores/' not in href:
                continue

            match_id_match = re.search(r'/live-cricket-scores/(\d+)/', href)
            if not match_id_match:
                continue

            match_id = match_id_match.group(1)
            live_matches[match_id] = match_link.get('title', '')

        logger.info(f'[POLL] Found {len(live_matches)} live matches on Cricbuzz')

        # Check for matches marked as "live" in the schedule document
        with state_lock:
            live_in_schedule = [mid for mid, data in matches_schedule.items() if data['status'] == 'live']

        if len(live_in_schedule) == 0:
            logger.debug('[POLL] 💤 No matches marked as LIVE in schedule - polling paused')
            return  # No matches to poll

        logger.info(f'[POLL] 🔥 Found {len(live_in_schedule)} match(es) marked as LIVE - polling now...')

        # Only poll for matches that are marked as live AND have webhooks
        matches_to_poll = [mid for mid in live_in_schedule if mid in webhooks]

        if len(matches_to_poll) == 0:
            logger.debug(f'[POLL] ℹ️  {len(live_in_schedule)} match(es) live but no webhooks registered - waiting...')
            return  # No webhooks for live matches

        logger.info(f'[POLL] ✅ Polling {len(matches_to_poll)} match(es) with registered webhooks')

        # Update polling state
        with state_lock:
            polling_state['last_check'] = datetime.now().isoformat()
            polling_state['active_matches'] = set(matches_to_poll)

        # Check each match marked as live in schedule for new events
        for match_id in matches_to_poll:
            # This match is already confirmed to have webhooks and be marked live

            # ⏰ Check if we've passed 12 AM cutoff for this match
            if should_stop_polling(match_id):
                with state_lock:
                    if match_id in matches_schedule:
                        matches_schedule[match_id]['status'] = 'completed'
                        logger.info(f'[AUTO] 🏁 Match {match_id} auto-marked COMPLETED (12 AM cutoff)')
                continue  # Skip polling this match

            logger.info(f'[POLL] Checking match {match_id} for new events...')

            # 🎲 CHECK FOR TOSS EVENT
            try:
                comm_url = f'https://www.cricbuzz.com/api/mcenter/comm/{match_id}'
                comm_resp = requests.get(comm_url, headers=HEADERS, timeout=5)
                if comm_resp.status_code == 200:
                    comm_data = comm_resp.json()
                    header = comm_data.get('matchHeader', {})

                    # Check toss state
                    current_state = header.get('state', '').lower()

                    # Get previous state from match_state
                    with state_lock:
                        prev_state = match_state.get(match_id, {}).get('match_state', '')

                    # Detect toss event (transition to "Toss" state)
                    if current_state == 'toss' and prev_state != 'toss':
                        toss_info = header.get('tossResults', {})
                        send_webhook_event(match_id, 'toss', {
                            'toss_winner': toss_info.get('tossWinnerName', ''),
                            'decision': toss_info.get('decision', ''),
                            'status': header.get('status', '')
                        })
                        logger.info(f'[POLL] 🎲 Toss detected: {toss_info.get("tossWinnerName")} opted to {toss_info.get("decision")}')

                        # Update state
                        with state_lock:
                            if match_id in match_state:
                                match_state[match_id]['match_state'] = 'toss'
                            else:
                                match_state[match_id] = {'match_state': 'toss', 'balls': [], 'last_timestamp': 0}

                    # Update match state tracking
                    with state_lock:
                        if match_id in match_state:
                            match_state[match_id]['match_state'] = current_state
                        else:
                            match_state[match_id] = {'match_state': current_state, 'balls': [], 'last_timestamp': 0}

            except Exception as e:
                logger.debug(f'[POLL] Error checking toss: {str(e)}')

            # Get ball-by-ball commentary with smart timestamp tracking
            try:
                commentary_data = []

                # Get last timestamp from state (for efficient pagination)
                with state_lock:
                    last_timestamp = match_state.get(match_id, {}).get('last_timestamp', 0)

                # Use last_timestamp if available, otherwise start from 0
                query_timestamp = last_timestamp if last_timestamp > 0 else 0

                logger.info(f'[POLL] Fetching data from timestamp: {query_timestamp} for match {match_id}')

                for innings_id in [2, 1]:
                    # Use smart timestamp: if we have previous data, fetch only newer data
                    # If not, use 0 to get initial data
                    url = f'https://www.cricbuzz.com/api/mcenter/commentary-pagination/{match_id}/{innings_id}/{query_timestamp}'
                    resp = requests.get(url, headers=HEADERS, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list):
                            commentary_data.extend(data)
                            # Update last timestamp from response
                            if data:
                                latest_item = data[-1]
                                if 'timestamp' in latest_item:
                                    new_timestamp = latest_item['timestamp']
                                    with state_lock:
                                        if match_id in match_state:
                                            match_state[match_id]['last_timestamp'] = new_timestamp
                                    logger.debug(f'[POLL] Updated last_timestamp to {new_timestamp} for match {match_id}')

                # Extract ball events
                current_balls = []
                for item in commentary_data:
                    if item.get('commType') == 'commentary' and 'ballMetric' in item:
                        current_balls.append({
                            'ball': str(item.get('ballMetric')),
                            'text': item.get('commText', ''),
                            'batsman': item.get('batsmanDetails', {}).get('playerName', ''),
                            'bowler': item.get('bowlerDetails', {}).get('playerName', ''),
                            'innings': item.get('inningsId')
                        })

                # Compare with previous state
                with state_lock:
                    prev_state = match_state.get(match_id, {'balls': [], 'match_state': ''})
                    prev_balls = prev_state.get('balls', [])

                    # Find new balls
                    new_balls = []
                    for curr_ball in current_balls:
                        if curr_ball not in prev_balls:
                            new_balls.append(curr_ball)

                    # Update state with balls and timestamp (preserve match_state)
                    match_state[match_id] = {
                        'balls': current_balls,
                        'last_timestamp': query_timestamp if current_balls else 0,
                        'match_state': match_state.get(match_id, {}).get('match_state', '')
                    }

                # Process new balls and send webhooks for filtered events
                for ball in new_balls:
                    text = ball['text'].lower()

                    # Check for events we care about
                    if '4' in text or 'four' in text or 'boundary 4' in text:
                        send_webhook_event(match_id, 'boundary', {
                            'type': '4',
                            'ball': ball['ball'],
                            'batsman': ball['batsman'],
                            'commentary': ball['text'][:500]
                        })
                        logger.info(f'[POLL] Detected 4 at {ball["ball"]} - {ball["batsman"]}')

                    if '6' in text or 'six' in text or 'boundary 6' in text:
                        send_webhook_event(match_id, 'boundary', {
                            'type': '6',
                            'ball': ball['ball'],
                            'batsman': ball['batsman'],
                            'commentary': ball['text'][:500]
                        })
                        logger.info(f'[POLL] Detected 6 at {ball["ball"]} - {ball["batsman"]}')

                    if 'wicket' in text or 'out' in text or 'caught' in text or 'bowled' in text or 'lbw' in text:
                        send_webhook_event(match_id, 'wicket', {
                            'ball': ball['ball'],
                            'batsman': ball['batsman'],
                            'bowler': ball['bowler'],
                            'commentary': ball['text'][:500]
                        })
                        logger.info(f'[POLL] Detected wicket at {ball["ball"]} - {ball["batsman"]}')

                    # Check for over boundaries in commentary
                    if 'end of' in text and 'over' in text:
                        over_match = re.search(r'end of (\d+(?:\.\d+)?)', text)
                        if over_match:
                            send_webhook_event(match_id, 'over_end', {
                                'over': over_match.group(1),
                                'ball': ball['ball'],
                                'commentary': ball['text'][:500]
                            })
                            logger.info(f'[POLL] Detected over end: {over_match.group(1)}')

                    # Check for innings events
                    if 'innings' in text:
                        if 'end of' in text or 'ends' in text:
                            send_webhook_event(match_id, 'innings_end', {
                                'innings': ball['innings'],
                                'commentary': ball['text'][:500]
                            })
                            logger.info(f'[POLL] Detected innings end - Innings {ball["innings"]}')
                        elif 'start' in text:
                            send_webhook_event(match_id, 'innings_start', {
                                'innings': ball['innings'],
                                'commentary': ball['text'][:500]
                            })
                            logger.info(f'[POLL] Detected innings start - Innings {ball["innings"]}')

                    # Check for match end in commentary (send event but don't rely on it for stopping)
                    if 'match' in text and ('won' in text or 'end' in text or 'finished' in text):
                        send_webhook_event(match_id, 'match_end', {
                            'commentary': ball['text'][:500]
                        })
                        logger.info(f'[POLL] Detected match end in commentary')

            except Exception as e:
                logger.error(f'[POLL] Error processing match {match_id}: {str(e)}')
                continue

    except Exception as e:
        logger.error(f'[POLL] Error in poll_live_matches: {str(e)}')

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/cricket/debug', methods=['GET'])
def debug():
    """Debug endpoint - shows HTML structure from Cricbuzz"""
    url = request.args.get('url', 'https://www.cricbuzz.com/cricket-match/ipl-2026')
    try:
        logger.info(f'[DEBUG] Fetching {url}')
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Try multiple selector patterns
        selectors_to_try = [
            ('div', {'class_': 'cb-col-100 cb-col'}),
            ('div', {'class_': 'cb-scrd-itm'}),
            ('div', {'class_': 'cb-match-item'}),
            ('div', {'class_': 'cb-schedules-list-item'}),
        ]

        debug_info = {
            'url': url,
            'page_title': soup.title.string if soup.title else 'No title',
            'selectors_found': {}
        }

        for tag, attrs in selectors_to_try:
            elements = soup.find_all(tag, attrs)
            debug_info['selectors_found'][str(attrs)] = len(elements)
            if elements and len(elements) > 0:
                debug_info['first_match_html'] = str(elements[0])[:800]

        # Also check for any match-like divs
        all_divs = soup.find_all('div')
        debug_info['total_divs'] = len(all_divs)

        return jsonify(debug_info)
    except Exception as e:
        return jsonify({'error': str(e), 'url': url}), 500

@app.route('/cricket/live', methods=['GET'])
def get_live_matches():
    """Get live cricket matches from Cricbuzz"""
    cached = get_from_cache('live-matches')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info('[FETCHING] Live matches from Cricbuzz')
        response = requests.get('https://www.cricbuzz.com/cricket-match/live-scores',
                              headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        matches = []

        # Find all match links - new structure: <a class="block mb-3" ...>
        match_links = soup.find_all('a', class_=re.compile(r'block\s+mb-3'))

        for match_link in match_links:
            try:
                href = match_link.get('href', '')
                if not href or '/live-cricket-scores/' not in href:
                    continue

                # Extract match ID from href: /live-cricket-scores/{id}/...
                match_id_match = re.search(r'/live-cricket-scores/(\d+)/', href)
                if not match_id_match:
                    continue

                match_id = match_id_match.group(1)

                # Get title and status from title attribute
                full_title = match_link.get('title', '')
                if not full_title:
                    continue

                # Parse title format: "Team1 vs Team2, Match - Status"
                # Extract status (last part after last dash)
                status = 'Live'
                if ' - ' in full_title:
                    status = full_title.split(' - ')[-1].strip()

                # Get match teams from inner text
                teams_div = match_link.find('div', class_='text-white')
                title = teams_div.text.strip() if teams_div else full_title

                matches.append({
                    'match_id': match_id,
                    'title': title,
                    'url': 'https://www.cricbuzz.com' + href if href else '',
                    'status': status,
                    'source': 'cricbuzz'
                })

            except Exception as e:
                logger.debug(f'Error parsing match: {str(e)}')
                continue

        result = {
            'matches': matches,
            'timestamp': datetime.now().isoformat(),
            'cache': 'MISS',
            'count': len(matches)
        }
        set_cache('live-matches', result)
        return jsonify(result)

    except Exception as e:
        logger.error(f'Error fetching live matches: {str(e)}')
        return jsonify({'error': f'Failed to fetch live matches: {str(e)}', 'matches': []}), 500

@app.route('/cricket/ipl/all', methods=['GET'])
def get_all_ipl_matches():
    """Get IPL matches from series page.

    NOTE: Cricbuzz uses infinite scroll to load matches dynamically.
    Initial HTML contains ~21 matches; remaining 49 load via JavaScript.
    Current implementation returns initial 21 matches from HTML.
    """
    cached = get_from_cache('ipl-all')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info('[FETCHING] All IPL matches from series page')

        url = 'https://www.cricbuzz.com/cricket-series/9241/indian-premier-league-2026/matches'
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        matches = []

        # Extract all match links from the page
        # Note: Only initial matches are in HTML; remaining require JavaScript/infinite scroll
        match_links = soup.find_all('a', href=re.compile(r'/live-cricket-scores/\d+'))

        seen_match_ids = set()
        for link in match_links:
            title = link.get('title', '')
            href = link.get('href', '')

            # Extract match ID
            match_id_match = re.search(r'/live-cricket-scores/(\d+)', href)
            if not match_id_match:
                continue

            match_id = match_id_match.group(1)

            # Avoid duplicates
            if match_id in seen_match_ids:
                continue
            seen_match_ids.add(match_id)

            # Parse match title to get status
            status = 'unknown'
            if 'Preview' in title:
                status = 'preview'
            elif 'Live' in title or 'Innings' in title or 'Break' in title:
                status = 'live'
            elif 'won' in title.lower() or 'complete' in title.lower():
                status = 'completed'

            matches.append({
                'match_id': match_id,
                'title': title,
                'status': status,
                'link': f'https://www.cricbuzz.com{href}'
            })

        result = {
            'matches': matches,
            'series_id': '9241',
            'series': 'IPL 2026',
            'timestamp': datetime.now().isoformat(),
            'cache': 'MISS',
            'count': len(matches),
            'limitation': 'Cricbuzz uses infinite scroll - returns initial ~21 matches from HTML. To get all 70 matches, need to discover the API endpoint that loads more matches on scroll.'
        }
        set_cache('ipl-all', result)
        return jsonify(result)

    except Exception as e:
        logger.error(f'Error fetching all IPL matches: {str(e)}')
        return jsonify({'error': f'Failed to fetch IPL matches: {str(e)}', 'matches': []}), 500

@app.route('/cricket/ipl', methods=['GET'])
def get_ipl_matches():
    """Get IPL 2026 matches from official URL"""
    cached = get_from_cache('ipl-matches')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info('[FETCHING] IPL 2026 matches from Cricbuzz')
        # Use official IPL 2026 URL
        response = requests.get('https://www.cricbuzz.com/cricket-series/9241/indian-premier-league-2026/matches',
                              headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        matches = []

        # Find all match links - new structure: <a class="block mb-3" ...>
        match_links = soup.find_all('a', class_=re.compile(r'block\s+mb-3'))

        for match_link in match_links:
            try:
                href = match_link.get('href', '')
                if not href or '/live-cricket-scores/' not in href:
                    continue

                # Extract match ID from href: /live-cricket-scores/{id}/...
                match_id_match = re.search(r'/live-cricket-scores/(\d+)/', href)
                if not match_id_match:
                    continue

                match_id = match_id_match.group(1)

                # Get title and status from title attribute
                full_title = match_link.get('title', '')
                if not full_title:
                    continue

                # Parse title format: "Team1 vs Team2, Match - Status"
                # Extract status (last part after last dash)
                status = 'Scheduled'
                if ' - ' in full_title:
                    status = full_title.split(' - ')[-1].strip()

                # Get match teams from inner text
                teams_div = match_link.find('div', class_='text-white')
                title = teams_div.text.strip() if teams_div else full_title

                matches.append({
                    'match_id': match_id,
                    'title': title,
                    'url': 'https://www.cricbuzz.com' + href if href else '',
                    'status': status,
                    'series': 'IPL 2026',
                    'source': 'cricbuzz'
                })

            except Exception as e:
                logger.debug(f'Error parsing IPL match: {str(e)}')
                continue

        result = {
            'matches': matches,
            'timestamp': datetime.now().isoformat(),
            'cache': 'MISS',
            'count': len(matches)
        }
        set_cache('ipl-matches', result)
        return jsonify(result)

    except Exception as e:
        logger.error(f'Error fetching IPL matches: {str(e)}')
        return jsonify({'error': f'Failed to fetch IPL matches: {str(e)}', 'matches': []}), 500

@app.route('/cricket/match/<match_id>', methods=['GET'])
def get_match_details(match_id):
    """Get detailed match score and result"""
    cached = get_from_cache(f'match-{match_id}')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info(f'[FETCHING] Match {match_id} scorecard')
        # Fetch from scorecard page to get full details
        url = f'https://www.cricbuzz.com/live-cricket-scorecard/{match_id}'
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract match result
        result_elem = soup.find('div', class_=re.compile(r'text-cbTextLink'))
        match_result = result_elem.text.strip() if result_elem else 'Match ongoing'

        # Extract scorecard data for each team/innings
        innings_data = []
        scorecard_divs = soup.find_all('div', id=re.compile(r'scard-team.*innings'))
        logger.info(f'[DEBUG] Found {len(scorecard_divs)} scorecard divs')

        for scorecard_div in scorecard_divs:
            try:
                # Extract team name and score - look for the header above scorecard
                team_name = 'Unknown'
                total_score = ''

                # Find team header
                parent = scorecard_div.find_parent('div', class_=re.compile(r'w-full'))
                if parent:
                    team_header = parent.find('div', class_=re.compile(r'hidden.*tb:block'))
                    if team_header:
                        team_name = team_header.text.strip()

                    # Find score (e.g., "201-9")
                    score_span = parent.find('span', class_=re.compile(r'font-bold'))
                    if score_span:
                        total_score = score_span.text.strip()

                # Extract batsmen stats
                batsmen = []
                # Find scorecard grid within this scorecard div
                grid_divs = scorecard_div.find_all('div', class_=re.compile(r'scorecard-bat-grid'))

                for row_idx, row_div in enumerate(grid_divs):
                    if row_idx == 0:  # Skip header row
                        continue
                    try:
                        # Player name from link
                        player_link = row_div.find('a', title=re.compile(r'View Profile'))
                        if not player_link:
                            continue

                        player_name = player_link.text.strip()

                        # How out (dismissal info)
                        dismissal_divs = row_div.find_all('div', class_=re.compile(r'text-cbTxtSec'))
                        how_out = dismissal_divs[0].text.strip() if dismissal_divs else 'Not Out'

                        # Stats columns: R, B, 4s, 6s, SR
                        stat_divs = row_div.find_all('div', class_=re.compile(r'flex.*justify-center.*items-center'))
                        if len(stat_divs) >= 5:
                            batsman = {
                                'name': player_name,
                                'runs': stat_divs[0].text.strip() if stat_divs[0] else '0',
                                'balls': stat_divs[1].text.strip() if stat_divs[1] else '0',
                                'fours': stat_divs[2].text.strip() if stat_divs[2] else '0',
                                'sixes': stat_divs[3].text.strip() if stat_divs[3] else '0',
                                'strike_rate': stat_divs[4].text.strip() if stat_divs[4] else '0',
                                'how_out': how_out
                            }
                            batsmen.append(batsman)
                    except Exception as e:
                        logger.debug(f'Error parsing batsman: {str(e)}')
                        continue

                if batsmen or total_score:
                    innings = {
                        'team': team_name,
                        'score': total_score,
                        'batsmen': batsmen
                    }
                    innings_data.append(innings)
            except Exception as e:
                logger.debug(f'Error parsing scorecard div: {str(e)}')
                continue

        # Extract player of the match
        potm_elem = soup.find('div', class_=re.compile(r'player.*match'))
        player_of_match = potm_elem.text.strip() if potm_elem else None

        result = {
            'match_id': match_id,
            'url': url,
            'result': match_result,
            'innings': innings_data,
            'player_of_match': player_of_match,
            'timestamp': datetime.now().isoformat(),
            'cache': 'MISS'
        }
        set_cache(f'match-{match_id}', result)
        return jsonify(result)

    except Exception as e:
        logger.error(f'Error fetching match {match_id}: {str(e)}')
        return jsonify({'error': f'Failed to fetch match: {str(e)}'}), 500

@app.route('/cricket/overs/<match_id>', methods=['GET'])
def get_overs(match_id):
    """Get over-by-over ball-by-ball data from Cricbuzz API"""
    cached = get_from_cache(f'overs-{match_id}')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info(f'[FETCHING] Overs data for match {match_id}')

        # First try innings 2 (chasing team, more recent data), then innings 1
        balls_data = []
        for innings_id in [2, 1]:
            # Use a recent timestamp to get latest balls (use 9999999999999 for most recent)
            url = f'https://www.cricbuzz.com/api/mcenter/commentary-pagination/{match_id}/{innings_id}/9999999999999'
            try:
                response = requests.get(url, headers=HEADERS, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        for item in data:
                            # Look for items with ball metrics (ballMetric field indicates a ball)
                            if 'ballMetric' in item and item.get('commType') == 'commentary':
                                ball_number = item.get('ballMetric')  # e.g., 19.3
                                commentary = item.get('commText', '')

                                # Extract result from over separator
                                result = '0'
                                if 'overSeparator' in item and item['overSeparator']:
                                    summary = item['overSeparator'].get('overSummary', '')
                                    # Parse runs from summary: "1 1 1 0 1 Wd 1"
                                    if summary:
                                        # Take the last ball's result
                                        runs = summary.strip().split()
                                        if runs:
                                            result = runs[-1]

                                ball_entry = {
                                    'ball': str(ball_number),
                                    'result': result,
                                    'commentary': commentary[:800],
                                    'innings': innings_id
                                }
                                balls_data.append(ball_entry)
            except Exception as e:
                logger.debug(f'Error fetching innings {innings_id}: {str(e)}')
                continue

        result = {
            'match_id': match_id,
            'source': 'Cricbuzz API',
            'balls': balls_data,
            'timestamp': datetime.now().isoformat(),
            'cache': 'MISS',
            'count': len(balls_data)
        }
        set_cache(f'overs-{match_id}', result)
        return jsonify(result)

    except Exception as e:
        logger.error(f'Error fetching overs for match {match_id}: {str(e)}')
        return jsonify({'error': f'Failed to fetch overs: {str(e)}', 'balls': []}), 500

@app.route('/cricket/commentary/<match_id>', methods=['GET'])
def get_commentary(match_id):
    """Get ball-by-ball full commentary from Cricbuzz API"""
    cached = get_from_cache(f'commentary-{match_id}')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info(f'[FETCHING] Commentary for match {match_id}')

        commentary_items = []

        # Try both innings (2 = chasing team, 1 = batting team)
        for innings_id in [2, 1]:
            # Use a high timestamp to get all recent commentary
            url = f'https://www.cricbuzz.com/api/mcenter/commentary-pagination/{match_id}/{innings_id}/9999999999999'
            try:
                response = requests.get(url, headers=HEADERS, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        for item in data:
                            # Filter for commentary items with ball info
                            if item.get('commType') == 'commentary' and 'ballMetric' in item:
                                ball_number = item.get('ballMetric')
                                commentary = item.get('commText', '')

                                # Get bowler and batsman details
                                batsman_name = ''
                                bowler_name = ''

                                if 'batsmanDetails' in item:
                                    batsman_name = item['batsmanDetails'].get('playerName', '')
                                if 'bowlerDetails' in item:
                                    bowler_name = item['bowlerDetails'].get('playerName', '')

                                # Extract result from over separator
                                result = '0'
                                if 'overSeparator' in item and item['overSeparator']:
                                    summary = item['overSeparator'].get('overSummary', '')
                                    if summary:
                                        runs = summary.strip().split()
                                        if runs:
                                            result = runs[-1]

                                # Remove HTML tags from commentary
                                clean_commentary = re.sub(r'<[^>]+>', '', commentary)
                                clean_commentary = ' '.join(clean_commentary.split())

                                comment_entry = {
                                    'ball': str(ball_number),
                                    'result': result,
                                    'bowler': bowler_name,
                                    'batsman': batsman_name,
                                    'commentary': clean_commentary[:1000],
                                    'innings': innings_id
                                }
                                commentary_items.append(comment_entry)
            except Exception as e:
                logger.debug(f'Error fetching innings {innings_id}: {str(e)}')
                continue

        result = {
            'match_id': match_id,
            'source': 'Cricbuzz API',
            'commentary': commentary_items,
            'timestamp': datetime.now().isoformat(),
            'cache': 'MISS',
            'count': len(commentary_items)
        }
        set_cache(f'commentary-{match_id}', result)
        return jsonify(result)

    except Exception as e:
        logger.error(f'Error fetching commentary for match {match_id}: {str(e)}')
        return jsonify({'error': f'Failed to fetch commentary: {str(e)}', 'commentary': []}), 500

@app.route('/cricket/summary/<match_id>', methods=['GET'])
def get_match_summary(match_id):
    """Get match summary - post-match interviews, highlights, videos"""
    cached = get_from_cache(f'summary-{match_id}')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info(f'[FETCHING] Match summary for {match_id}')

        # Cricbuzz summary API - returns post-match content
        url = f'https://www.cricbuzz.com/api/mcenter/comm/{match_id}'
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        data = response.json()
        summary_items = []

        # Parse matchCommentary object
        if 'matchCommentary' in data:
            for item_id, item in data['matchCommentary'].items():
                comm_type = item.get('commType')
                comm_text = item.get('commText', '')

                if comm_type == 'commentary':
                    # Post-match commentary (interviews, analysis)
                    summary_items.append({
                        'timestamp': item.get('timestamp'),
                        'type': 'commentary',
                        'text': comm_text[:1000],
                        'team': item.get('teamName', ''),
                        'innings': item.get('inningsId')
                    })
                elif comm_type == 'snippet':
                    # Video highlights/snippets
                    summary_items.append({
                        'timestamp': item.get('timestamp'),
                        'type': 'video',
                        'headline': item.get('headline', ''),
                        'video_url': item.get('videoUrl', ''),
                        'item_id': item.get('itemId')
                    })

        result = {
            'match_id': match_id,
            'source': 'Cricbuzz API',
            'summary': summary_items,
            'timestamp': datetime.now().isoformat(),
            'cache': 'MISS',
            'count': len(summary_items)
        }
        set_cache(f'summary-{match_id}', result)
        return jsonify(result)

    except Exception as e:
        logger.error(f'Error fetching summary for match {match_id}: {str(e)}')
        return jsonify({'error': f'Failed to fetch summary: {str(e)}', 'summary': []}), 500

@app.route('/cricket/points-table/<series_id>', methods=['GET'])
def get_points_table(series_id):
    """Get points table standings for a series"""
    cached = get_from_cache(f'points-table-{series_id}')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info(f'[FETCHING] Points table for series {series_id}')
        url = f'https://www.cricbuzz.com/cricket-series/{series_id}/points-table'

        # Use Playwright to fetch the page with JavaScript rendering
        html = fetch_with_playwright(url, wait_selector='div[class*="grid"]')
        if not html:
            return jsonify({'error': 'Failed to fetch page with Playwright', 'standings': []}), 500

        soup = BeautifulSoup(html, 'html.parser')
        standings = []

        # Find all point table grid rows
        table_rows = soup.find_all('div', class_=re.compile(r'grid.*point|point.*grid'))

        # If not found, try broader pattern
        if not table_rows:
            table_rows = soup.find_all('div', class_=re.compile(r'grid'))

        logger.info(f'[DEBUG] Found {len(table_rows)} potential table rows')

        # Skip header row and process team rows
        header_found = False
        for row in table_rows:
            try:
                # Get all divs in this row
                divs = row.find_all('div', recursive=False)  # Direct children only
                row_text = row.get_text()

                if not header_found:
                    # Check if this is header row by looking for "Teams" or column headers
                    if any(header_text in row_text for header_text in ['Teams', 'Rank', 'Team', 'Played']):
                        header_found = True
                    continue

                # If we have the header, process team rows
                if len(divs) >= 6:
                    try:
                        # Extract basic info
                        row_divs = row.find_all('div')
                        row_text_parts = [div.get_text(strip=True) for div in row_divs]

                        # Filter empty strings
                        row_data = [text for text in row_text_parts if text]

                        if len(row_data) >= 6:
                            team_entry = {
                                'rank': row_data[0] if row_data else '0',
                                'team': row_data[1] if len(row_data) > 1 else 'Unknown',
                                'played': row_data[2] if len(row_data) > 2 else '0',
                                'won': row_data[3] if len(row_data) > 3 else '0',
                                'lost': row_data[4] if len(row_data) > 4 else '0',
                                'points': row_data[5] if len(row_data) > 5 else '0',
                                'nrr': row_data[6] if len(row_data) > 6 else '0.000'
                            }
                            standings.append(team_entry)
                    except Exception as e:
                        logger.debug(f'Error processing row data: {str(e)}')
                        continue
            except Exception as e:
                logger.debug(f'Error parsing standings row: {str(e)}')
                continue

        result = {
            'series_id': series_id,
            'url': url,
            'standings': standings,
            'timestamp': datetime.now().isoformat(),
            'cache': 'MISS',
            'count': len(standings)
        }
        set_cache(f'points-table-{series_id}', result)
        return jsonify(result)

    except Exception as e:
        logger.error(f'Error fetching points table for series {series_id}: {str(e)}')
        return jsonify({'error': f'Failed to fetch points table: {str(e)}', 'standings': []}), 500

@app.route('/webhook/register', methods=['POST'])
def register_webhook():
    """Register webhook for match events"""
    try:
        data = request.get_json()
        webhook_url = data.get('webhook_url')
        match_id = data.get('match_id')

        if not webhook_url or not match_id:
            return jsonify({'error': 'webhook_url and match_id required'}), 400

        # Store webhook
        if match_id not in webhooks:
            webhooks[match_id] = []

        if webhook_url not in webhooks[match_id]:
            webhooks[match_id].append(webhook_url)

        logger.info(f'[WEBHOOK] Registered webhook for match {match_id}: {webhook_url}')

        return jsonify({
            'status': 'registered',
            'match_id': match_id,
            'webhook_url': webhook_url,
            'total_webhooks': len(webhooks[match_id])
        }), 201

    except Exception as e:
        logger.error(f'Error registering webhook: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/webhook/list/<match_id>', methods=['GET'])
def list_webhooks(match_id):
    """List webhooks for a match"""
    return jsonify({
        'match_id': match_id,
        'webhooks': webhooks.get(match_id, []),
        'count': len(webhooks.get(match_id, []))
    })

@app.route('/webhook/send', methods=['POST'])
def send_webhook_event():
    """Send event to all registered webhooks for a match"""
    try:
        data = request.get_json()
        match_id = data.get('match_id')
        event_type = data.get('event_type')  # 'ball', 'wicket', 'boundary', 'over', 'match_start', 'match_end'
        event_data = data.get('event_data', {})

        if not match_id or not event_type:
            return jsonify({'error': 'match_id and event_type required'}), 400

        # Get webhooks for this match
        match_webhooks = webhooks.get(match_id, [])
        if not match_webhooks:
            return jsonify({'error': f'No webhooks registered for match {match_id}'}), 404

        # Prepare webhook payload
        payload = {
            'match_id': match_id,
            'event_type': event_type,
            'event_data': event_data,
            'timestamp': datetime.now().isoformat()
        }

        # Send to all webhooks
        sent = 0
        failed = 0
        for webhook_url in match_webhooks:
            try:
                response = requests.post(webhook_url, json=payload, timeout=5)
                if response.status_code in [200, 201, 202]:
                    sent += 1
                    logger.info(f'[WEBHOOK] Sent {event_type} event to {webhook_url}')
                else:
                    failed += 1
                    logger.warning(f'[WEBHOOK] Failed to send to {webhook_url}: {response.status_code}')
            except Exception as e:
                failed += 1
                logger.error(f'[WEBHOOK] Error sending to {webhook_url}: {str(e)}')

        return jsonify({
            'status': 'sent',
            'match_id': match_id,
            'event_type': event_type,
            'sent': sent,
            'failed': failed,
            'total': len(match_webhooks)
        })

    except Exception as e:
        logger.error(f'Error sending webhook event: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/polling/status', methods=['GET'])
def polling_status():
    """Get current polling status and active matches"""
    with state_lock:
        return jsonify({
            'polling_mode': polling_state['polling_mode'],
            'active_matches': list(polling_state['active_matches']),
            'active_match_count': len(polling_state['active_matches']),
            'registered_webhooks': sum(len(urls) for urls in webhooks.values()),
            'last_check': polling_state['last_check'],
            'timestamp': datetime.now().isoformat(),
            'status': '🔥 INTENSIVE' if polling_state['polling_mode'] == 'intensive' else '💤 LIGHT'
        })

@app.route('/polling/start', methods=['POST'])
def start_intensive_polling():
    """Manually trigger intensive polling (for testing)"""
    with state_lock:
        polling_state['polling_mode'] = 'intensive'
        logger.info('[MANUAL] Intensive polling activated')
    return jsonify({'status': 'Intensive polling activated', 'mode': 'intensive'})

@app.route('/schedule/load-ipl', methods=['POST'])
def load_ipl_schedule():
    """Load ALL IPL matches from Cricbuzz and populate matches_schedule doc"""
    try:
        logger.info('[SCHEDULE] 📥 Loading ALL IPL matches from Cricbuzz...')

        # Get all IPL matches from series page
        url = 'https://www.cricbuzz.com/cricket-series/9241/indian-premier-league-2026/matches'
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all match links - both initial loaded and all referenced in page
        match_links = soup.find_all('a', href=re.compile(r'/live-cricket-scores/\d+'))

        # Also try to find match links in different formats
        all_match_links = []
        all_match_links.extend(match_links)

        # Get unique matches
        seen_ids = set()
        matches_data = []

        for link in all_match_links:
            title = link.get('title', '').strip()
            href = link.get('href', '').strip()

            if not title or not href:
                continue

            match_id_match = re.search(r'/live-cricket-scores/(\d+)', href)
            if not match_id_match:
                continue

            match_id = match_id_match.group(1)

            # Skip duplicates
            if match_id in seen_ids:
                continue
            seen_ids.add(match_id)

            # Determine status from title
            status = 'scheduled'
            if 'Live' in title or 'Innings' in title or 'Break' in title:
                status = 'live'
            elif 'won' in title.lower() or 'complete' in title.lower() or 'ended' in title.lower():
                status = 'completed'
            elif 'preview' in title.lower():
                status = 'scheduled'

            # Extract team names and match info
            teams = 'vs'.join([t.strip() for t in title.split('vs')[:2]]) if 'vs' in title else title

            matches_data.append({
                'match_id': match_id,
                'title': title,
                'teams': teams,
                'status': status,
                'url': f'https://www.cricbuzz.com{href}'
            })

        # Populate schedule document
        loaded_count = 0
        with state_lock:
            for match in matches_data:
                match_id = match['match_id']

                # Update or create
                matches_schedule[match_id] = {
                    'match_id': match_id,
                    'title': match['title'],
                    'teams': match['teams'],
                    'status': match['status'],
                    'url': match['url'],
                    'created_at': datetime.now().isoformat(),
                    'webhooks_registered': len(webhooks.get(match_id, []))
                }
                loaded_count += 1

        logger.info(f'[SCHEDULE] ✅ Loaded {loaded_count} IPL matches into schedule document')

        return jsonify({
            'status': 'success',
            'message': f'Loaded {loaded_count} IPL matches',
            'matches_loaded': loaded_count,
            'total_in_schedule': len(matches_schedule),
            'breakdown': {
                'scheduled': sum(1 for m in matches_schedule.values() if m['status'] == 'scheduled'),
                'live': sum(1 for m in matches_schedule.values() if m['status'] == 'live'),
                'completed': sum(1 for m in matches_schedule.values() if m['status'] == 'completed')
            }
        }), 201

    except Exception as e:
        logger.error(f'Error loading IPL schedule: {str(e)}')
        return jsonify({'error': str(e), 'details': str(e)}), 500

@app.route('/schedule/list', methods=['GET'])
def get_schedule():
    """Get current matches schedule document"""
    with state_lock:
        scheduled = {mid: m for mid, m in matches_schedule.items() if m['status'] == 'scheduled'}
        live = {mid: m for mid, m in matches_schedule.items() if m['status'] == 'live'}
        completed = {mid: m for mid, m in matches_schedule.items() if m['status'] == 'completed'}

        return jsonify({
            'scheduled_count': len(scheduled),
            'live_count': len(live),
            'completed_count': len(completed),
            'scheduled_matches': list(scheduled.values()),
            'live_matches': list(live.values()),
            'total_in_doc': len(matches_schedule)
        })

@app.route('/schedule/add-matches', methods=['POST'])
def add_matches_to_schedule():
    """Add matches from web search data to schedule document

    Expected JSON format:
    {
        "matches": [
            {
                "match_num": 1,
                "date": "Mar 28",
                "teams": "RCB vs SRH",
                "time": "7:30 PM IST",
                "venue": "Bengaluru"
            },
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        matches = data.get('matches', [])

        if not matches:
            return jsonify({'error': 'No matches provided'}), 400

        added_count = 0
        with state_lock:
            for match in matches:
                # Create unique match identifier from match number
                match_num = match.get('match_num') or match.get('match_number') or added_count + 1
                match_id = f"ipl2026_m{match_num}"

                # Skip if already exists
                if match_id in matches_schedule:
                    continue

                teams = match.get('teams', '')
                date_str = match.get('date', '')
                time_str = match.get('time', '')
                venue = match.get('venue', '')

                # Default status is scheduled
                status = 'scheduled'

                matches_schedule[match_id] = {
                    'match_id': match_id,
                    'match_num': match_num,
                    'teams': teams,
                    'date': date_str,
                    'time': time_str,
                    'venue': venue,
                    'status': status,
                    'created_at': datetime.now().isoformat(),
                    'webhooks_registered': 0
                }
                added_count += 1

        logger.info(f'[SCHEDULE] ✅ Added {added_count} matches to schedule document')

        return jsonify({
            'status': 'success',
            'added': added_count,
            'total_in_schedule': len(matches_schedule)
        }), 201

    except Exception as e:
        logger.error(f'Error adding matches: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/schedule/bulk-load', methods=['POST'])
def bulk_load_ipl_schedule():
    """Bulk load ALL 70 IPL 2026 matches from official BCCI schedule"""
    try:
        logger.info('[SCHEDULE] 📥 Bulk loading ALL 70 IPL 2026 matches from PDF...')

        # Complete IPL 2026 schedule - all 70 matches from official BCCI PDF
        ipl_matches = [
            {"match_num": 1, "date": "28-MAR-26", "teams": "RCB vs SRH", "time": "7:30 PM IST", "venue": "Bengaluru"},
            {"match_num": 2, "date": "29-MAR-26", "teams": "MI vs KKR", "time": "7:30 PM IST", "venue": "Mumbai"},
            {"match_num": 3, "date": "30-MAR-26", "teams": "RR vs CSK", "time": "7:30 PM IST", "venue": "Guwahati"},
            {"match_num": 4, "date": "31-MAR-26", "teams": "PBKS vs GT", "time": "7:30 PM IST", "venue": "New Chandigarh"},
            {"match_num": 5, "date": "01-APR-26", "teams": "LSG vs DC", "time": "7:30 PM IST", "venue": "Lucknow"},
            {"match_num": 6, "date": "02-APR-26", "teams": "KKR vs SRH", "time": "7:30 PM IST", "venue": "Kolkata"},
            {"match_num": 7, "date": "03-APR-26", "teams": "CSK vs PBKS", "time": "7:30 PM IST", "venue": "Chennai"},
            {"match_num": 8, "date": "04-APR-26", "teams": "DC vs MI", "time": "3:30 PM IST", "venue": "Delhi"},
            {"match_num": 9, "date": "04-APR-26", "teams": "GT vs RR", "time": "7:30 PM IST", "venue": "Ahmedabad"},
            {"match_num": 10, "date": "05-APR-26", "teams": "SRH vs LSG", "time": "3:30 PM IST", "venue": "Hyderabad"},
            {"match_num": 11, "date": "05-APR-26", "teams": "RCB vs CSK", "time": "7:30 PM IST", "venue": "Bengaluru"},
            {"match_num": 12, "date": "06-APR-26", "teams": "KKR vs PBKS", "time": "7:30 PM IST", "venue": "Kolkata"},
            {"match_num": 13, "date": "07-APR-26", "teams": "RR vs MI", "time": "7:30 PM IST", "venue": "Guwahati"},
            {"match_num": 14, "date": "08-APR-26", "teams": "DC vs GT", "time": "7:30 PM IST", "venue": "Delhi"},
            {"match_num": 15, "date": "09-APR-26", "teams": "KKR vs LSG", "time": "7:30 PM IST", "venue": "Kolkata"},
            {"match_num": 16, "date": "10-APR-26", "teams": "RR vs RCB", "time": "7:30 PM IST", "venue": "Guwahati"},
            {"match_num": 17, "date": "11-APR-26", "teams": "PBKS vs SRH", "time": "3:30 PM IST", "venue": "New Chandigarh"},
            {"match_num": 18, "date": "11-APR-26", "teams": "CSK vs DC", "time": "7:30 PM IST", "venue": "Chennai"},
            {"match_num": 19, "date": "12-APR-26", "teams": "LSG vs GT", "time": "3:30 PM IST", "venue": "Lucknow"},
            {"match_num": 20, "date": "12-APR-26", "teams": "MI vs RCB", "time": "7:30 PM IST", "venue": "Mumbai"},
            {"match_num": 21, "date": "13-APR-26", "teams": "SRH vs RR", "time": "7:30 PM IST", "venue": "Hyderabad"},
            {"match_num": 22, "date": "14-APR-26", "teams": "CSK vs KKR", "time": "7:30 PM IST", "venue": "Chennai"},
            {"match_num": 23, "date": "15-APR-26", "teams": "RCB vs LSG", "time": "7:30 PM IST", "venue": "Bengaluru"},
            {"match_num": 24, "date": "16-APR-26", "teams": "MI vs PBKS", "time": "7:30 PM IST", "venue": "Mumbai"},
            {"match_num": 25, "date": "17-APR-26", "teams": "GT vs KKR", "time": "7:30 PM IST", "venue": "Ahmedabad"},
            {"match_num": 26, "date": "18-APR-26", "teams": "RCB vs DC", "time": "3:30 PM IST", "venue": "Bengaluru"},
            {"match_num": 27, "date": "18-APR-26", "teams": "SRH vs CSK", "time": "7:30 PM IST", "venue": "Hyderabad"},
            {"match_num": 28, "date": "19-APR-26", "teams": "KKR vs RR", "time": "3:30 PM IST", "venue": "Kolkata"},
            {"match_num": 29, "date": "19-APR-26", "teams": "PBKS vs LSG", "time": "7:30 PM IST", "venue": "New Chandigarh"},
            {"match_num": 30, "date": "20-APR-26", "teams": "GT vs MI", "time": "7:30 PM IST", "venue": "Ahmedabad"},
            {"match_num": 31, "date": "21-APR-26", "teams": "SRH vs DC", "time": "7:30 PM IST", "venue": "Hyderabad"},
            {"match_num": 32, "date": "22-APR-26", "teams": "LSG vs RR", "time": "7:30 PM IST", "venue": "Lucknow"},
            {"match_num": 33, "date": "23-APR-26", "teams": "MI vs CSK", "time": "7:30 PM IST", "venue": "Mumbai"},
            {"match_num": 34, "date": "24-APR-26", "teams": "RCB vs GT", "time": "7:30 PM IST", "venue": "Bengaluru"},
            {"match_num": 35, "date": "25-APR-26", "teams": "DC vs PBKS", "time": "3:30 PM IST", "venue": "Delhi"},
            {"match_num": 36, "date": "25-APR-26", "teams": "RR vs SRH", "time": "7:30 PM IST", "venue": "Jaipur"},
            {"match_num": 37, "date": "26-APR-26", "teams": "GT vs CSK", "time": "3:30 PM IST", "venue": "Ahmedabad"},
            {"match_num": 38, "date": "26-APR-26", "teams": "LSG vs KKR", "time": "7:30 PM IST", "venue": "Lucknow"},
            {"match_num": 39, "date": "27-APR-26", "teams": "DC vs RCB", "time": "7:30 PM IST", "venue": "Delhi"},
            {"match_num": 40, "date": "28-APR-26", "teams": "PBKS vs RR", "time": "7:30 PM IST", "venue": "New Chandigarh"},
            {"match_num": 41, "date": "29-APR-26", "teams": "MI vs SRH", "time": "7:30 PM IST", "venue": "Mumbai"},
            {"match_num": 42, "date": "30-APR-26", "teams": "GT vs RCB", "time": "7:30 PM IST", "venue": "Ahmedabad"},
            {"match_num": 43, "date": "01-MAY-26", "teams": "RR vs DC", "time": "7:30 PM IST", "venue": "Jaipur"},
            {"match_num": 44, "date": "02-MAY-26", "teams": "CSK vs MI", "time": "7:30 PM IST", "venue": "Chennai"},
            {"match_num": 45, "date": "03-MAY-26", "teams": "SRH vs KKR", "time": "3:30 PM IST", "venue": "Hyderabad"},
            {"match_num": 46, "date": "03-MAY-26", "teams": "GT vs PBKS", "time": "7:30 PM IST", "venue": "Ahmedabad"},
            {"match_num": 47, "date": "04-MAY-26", "teams": "MI vs LSG", "time": "7:30 PM IST", "venue": "Mumbai"},
            {"match_num": 48, "date": "05-MAY-26", "teams": "DC vs CSK", "time": "7:30 PM IST", "venue": "Delhi"},
            {"match_num": 49, "date": "06-MAY-26", "teams": "SRH vs PBKS", "time": "7:30 PM IST", "venue": "Hyderabad"},
            {"match_num": 50, "date": "07-MAY-26", "teams": "LSG vs RCB", "time": "7:30 PM IST", "venue": "Lucknow"},
            {"match_num": 51, "date": "08-MAY-26", "teams": "DC vs KKR", "time": "7:30 PM IST", "venue": "Delhi"},
            {"match_num": 52, "date": "09-MAY-26", "teams": "RR vs GT", "time": "7:30 PM IST", "venue": "Jaipur"},
            {"match_num": 53, "date": "10-MAY-26", "teams": "CSK vs LSG", "time": "3:30 PM IST", "venue": "Chennai"},
            {"match_num": 54, "date": "10-MAY-26", "teams": "RCB vs MI", "time": "7:30 PM IST", "venue": "Raipur"},
            {"match_num": 55, "date": "11-MAY-26", "teams": "PBKS vs DC", "time": "7:30 PM IST", "venue": "Dharamshala"},
            {"match_num": 56, "date": "12-MAY-26", "teams": "GT vs SRH", "time": "7:30 PM IST", "venue": "Ahmedabad"},
            {"match_num": 57, "date": "13-MAY-26", "teams": "RCB vs KKR", "time": "7:30 PM IST", "venue": "Raipur"},
            {"match_num": 58, "date": "14-MAY-26", "teams": "PBKS vs MI", "time": "7:30 PM IST", "venue": "Dharamshala"},
            {"match_num": 59, "date": "15-MAY-26", "teams": "LSG vs CSK", "time": "7:30 PM IST", "venue": "Lucknow"},
            {"match_num": 60, "date": "16-MAY-26", "teams": "KKR vs GT", "time": "7:30 PM IST", "venue": "Kolkata"},
            {"match_num": 61, "date": "17-MAY-26", "teams": "PBKS vs RCB", "time": "3:30 PM IST", "venue": "Dharamshala"},
            {"match_num": 62, "date": "17-MAY-26", "teams": "DC vs RR", "time": "7:30 PM IST", "venue": "Delhi"},
            {"match_num": 63, "date": "18-MAY-26", "teams": "CSK vs SRH", "time": "7:30 PM IST", "venue": "Chennai"},
            {"match_num": 64, "date": "19-MAY-26", "teams": "RR vs LSG", "time": "7:30 PM IST", "venue": "Jaipur"},
            {"match_num": 65, "date": "20-MAY-26", "teams": "KKR vs MI", "time": "7:30 PM IST", "venue": "Kolkata"},
            {"match_num": 66, "date": "21-MAY-26", "teams": "CSK vs GT", "time": "7:30 PM IST", "venue": "Chennai"},
            {"match_num": 67, "date": "22-MAY-26", "teams": "SRH vs RCB", "time": "7:30 PM IST", "venue": "Hyderabad"},
            {"match_num": 68, "date": "23-MAY-26", "teams": "LSG vs PBKS", "time": "7:30 PM IST", "venue": "Lucknow"},
            {"match_num": 69, "date": "24-MAY-26", "teams": "MI vs RR", "time": "7:30 PM IST", "venue": "Mumbai"},
            {"match_num": 70, "date": "24-MAY-26", "teams": "KKR vs DC", "time": "7:30 PM IST", "venue": "Kolkata"},
        ]

        loaded_count = 0
        with state_lock:
            for match in ipl_matches:
                match_num = match['match_num']
                match_id = f"ipl2026_m{match_num}"

                matches_schedule[match_id] = {
                    'match_id': match_id,
                    'match_num': match_num,
                    'teams': match['teams'],
                    'date': match['date'],
                    'time': match['time'],
                    'venue': match['venue'],
                    'status': 'scheduled',
                    'created_at': datetime.now().isoformat(),
                    'webhooks_registered': 0
                }
                loaded_count += 1

        logger.info(f'[SCHEDULE] ✅ Loaded {loaded_count} IPL 2026 matches into schedule document')

        return jsonify({
            'status': 'success',
            'message': f'Loaded {loaded_count} IPL 2026 matches from web search',
            'matches_loaded': loaded_count,
            'total_in_schedule': len(matches_schedule),
            'note': 'Matches 1-25 loaded. Additional matches (26-70) can be added via /schedule/add-matches endpoint',
            'breakdown': {
                'scheduled': sum(1 for m in matches_schedule.values() if m['status'] == 'scheduled'),
                'live': sum(1 for m in matches_schedule.values() if m['status'] == 'live'),
                'completed': sum(1 for m in matches_schedule.values() if m['status'] == 'completed')
            }
        }), 201

    except Exception as e:
        logger.error(f'Error bulk loading schedule: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/schedule/update-status', methods=['POST'])
def update_match_status():
    """Update match status in schedule document"""
    try:
        data = request.get_json()
        match_id = data.get('match_id')
        status = data.get('status')  # 'scheduled', 'live', 'completed', 'cancelled'

        if not match_id or not status:
            return jsonify({'error': 'match_id and status required'}), 400

        valid_statuses = ['scheduled', 'live', 'completed', 'cancelled']
        if status not in valid_statuses:
            return jsonify({'error': f'status must be one of: {valid_statuses}'}), 400

        with state_lock:
            if match_id not in matches_schedule:
                return jsonify({'error': f'Match {match_id} not in schedule'}), 404

            old_status = matches_schedule[match_id]['status']
            matches_schedule[match_id]['status'] = status
            matches_schedule[match_id]['updated_at'] = datetime.now().isoformat()

            logger.info(f'[SCHEDULE] Updated match {match_id}: {old_status} → {status}')

            # If match just ended, log it
            if old_status in ['live', 'scheduled'] and status == 'completed':
                logger.info(f'[SCHEDULE] 🏁 Match {match_id} COMPLETED - polling can stop')

        return jsonify({
            'status': 'updated',
            'match_id': match_id,
            'old_status': old_status,
            'new_status': status
        })

    except Exception as e:
        logger.error(f'Error updating status: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/schedule/check-cutoff/<match_id>', methods=['GET'])
def check_cutoff_endpoint(match_id):
    """Check if match has reached 12 AM cutoff for polling"""
    try:
        should_stop = should_stop_polling(match_id)

        with state_lock:
            match_info = matches_schedule.get(match_id, {})

        return jsonify({
            'match_id': match_id,
            'start_time': match_info.get('start_time'),
            'should_stop_polling': should_stop,
            'current_time': datetime.now().isoformat(),
            'message': '12 AM cutoff reached' if should_stop else 'Still within polling window'
        })

    except Exception as e:
        logger.error(f'Error checking cutoff: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Internal server error'}), 500

def init_scheduler():
    """Initialize background scheduler - polls ONLY during scheduled match times"""
    scheduler = BackgroundScheduler()

    # Add intensive polling job - runs every 1 minute
    # Only polls when matches are marked as "live" in the schedule document
    scheduler.add_job(
        poll_live_matches,
        'interval',
        minutes=1,
        id='poll_matches',
        name='Match Polling (1 min - only when matches are live)'
    )

    scheduler.start()
    logger.info('[SCHEDULER] ✅ Smart polling initialized!')
    logger.info('[SCHEDULER] Polling strategy: Only when matches are marked LIVE in schedule')
    logger.info('[SCHEDULER] How to use:')
    logger.info('[SCHEDULER]   1. When match starts: POST /schedule/update-status → status: "live"')
    logger.info('[SCHEDULER]   2. Polling auto-starts every 1 minute')
    logger.info('[SCHEDULER]   3. When match ends: POST /schedule/update-status → status: "completed"')
    logger.info('[SCHEDULER]   4. Polling auto-stops')
    return scheduler

if __name__ == '__main__':
    import os
    port = int(os.getenv('PORT', 3000))
    logger.info(f'🏏 Cricket Python proxy starting on port {port}')

    # Start background scheduler for polling
    scheduler = init_scheduler()

    try:
        app.run(host='0.0.0.0', port=port, debug=False)
    finally:
        if scheduler.running:
            scheduler.shutdown()
