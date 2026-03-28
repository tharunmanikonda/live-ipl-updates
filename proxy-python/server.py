from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

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

        soup = BeautifulSoup(response.text, 'html.parser')
        matches = []

        # Find all match containers
        for match_element in soup.find_all('div', class_='cb-col-100 cb-col'):
            try:
                # Get match title and ID
                title_elem = match_element.find('a', class_='cb-lv-scr-mtch-hdr')
                if not title_elem:
                    continue

                title = title_elem.text.strip()
                href = title_elem.get('href', '')

                # Extract match ID
                import re
                match_id_match = re.search(r'/(\d+)/', href)
                if not match_id_match:
                    continue

                match_id = match_id_match.group(1)

                # Get teams and scores
                teams = []
                team_elements = match_element.find_all('div', class_='cb-ovr-flo cb-hmscg-tm-nm')
                for i, team_elem in enumerate(team_elements):
                    team_name = team_elem.text.strip()
                    teams.append({'name': team_name, 'score': ''})

                # Get status
                status_elem = match_element.find('div', class_='cb-text-live')
                if not status_elem:
                    status_elem = match_element.find('div', class_='cb-text-complete')
                status = status_elem.text.strip() if status_elem else 'Scheduled'

                matches.append({
                    'match_id': match_id,
                    'title': title,
                    'teams': teams,
                    'status': status,
                    'source': 'cricbuzz'
                })
            except Exception as e:
                logger.error(f'Error parsing match: {str(e)}')
                continue

        result = {
            'matches': matches,
            'timestamp': datetime.now().isoformat(),
            'cache': 'MISS'
        }
        set_cache('live-matches', result)
        return jsonify(result)

    except Exception as e:
        logger.error(f'Error fetching live matches: {str(e)}')
        return jsonify({'error': f'Failed to fetch live matches: {str(e)}'}), 500

@app.route('/cricket/ipl', methods=['GET'])
def get_ipl_matches():
    """Get IPL 2026 matches"""
    cached = get_from_cache('ipl-matches')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info('[FETCHING] IPL 2026 matches from Cricbuzz')
        response = requests.get('https://www.cricbuzz.com/cricket-match/ipl-2026',
                              headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        matches = []

        for match_element in soup.find_all('div', class_='cb-col-100 cb-col'):
            try:
                title_elem = match_element.find('a', class_='cb-lv-scr-mtch-hdr')
                if not title_elem or 'IPL' not in title_elem.text:
                    continue

                title = title_elem.text.strip()
                href = title_elem.get('href', '')

                import re
                match_id_match = re.search(r'/(\d+)/', href)
                if not match_id_match:
                    continue

                match_id = match_id_match.group(1)

                teams = []
                team_elements = match_element.find_all('div', class_='cb-ovr-flo cb-hmscg-tm-nm')
                for team_elem in team_elements:
                    teams.append({'name': team_elem.text.strip()})

                status_elem = match_element.find('div', class_='cb-text-live')
                if not status_elem:
                    status_elem = match_element.find('div', class_='cb-text-complete')
                status = status_elem.text.strip() if status_elem else 'Upcoming'

                matches.append({
                    'match_id': match_id,
                    'title': title,
                    'teams': teams,
                    'status': status,
                    'series': 'IPL 2026',
                    'source': 'cricbuzz'
                })
            except Exception as e:
                logger.error(f'Error parsing IPL match: {str(e)}')
                continue

        result = {
            'matches': matches,
            'timestamp': datetime.now().isoformat(),
            'cache': 'MISS'
        }
        set_cache('ipl-matches', result)
        return jsonify(result)

    except Exception as e:
        logger.error(f'Error fetching IPL matches: {str(e)}')
        return jsonify({'error': f'Failed to fetch IPL matches: {str(e)}'}), 500

@app.route('/cricket/match/<match_id>', methods=['GET'])
def get_match_details(match_id):
    """Get detailed match score"""
    cached = get_from_cache(f'match-{match_id}')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info(f'[FETCHING] Match {match_id} details')
        url = f'https://www.cricbuzz.com/live-cricket-scorecard/{match_id}'
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract title
        title_elem = soup.find('div', class_='cb-nav-hdr cb-font-18')
        title = title_elem.text.strip().replace(', Commentary', '') if title_elem else 'Match'

        # Extract live score
        score_elem = soup.find('div', class_='cb-font-20 text-bold')
        live_score = score_elem.text.strip() if score_elem else 'N/A'

        result = {
            'match_id': match_id,
            'title': title,
            'score': live_score,
            'timestamp': datetime.now().isoformat(),
            'cache': 'MISS'
        }
        set_cache(f'match-{match_id}', result)
        return jsonify(result)

    except Exception as e:
        logger.error(f'Error fetching match {match_id}: {str(e)}')
        return jsonify({'error': f'Failed to fetch match: {str(e)}'}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    logger.info('🏏 Cricket Python proxy starting on port 3000')
    app.run(host='0.0.0.0', port=3000, debug=False)
