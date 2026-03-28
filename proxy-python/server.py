from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import re
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

        # Use proven selectors from MCP server
        container = soup.find('div', id='page-wrapper')
        if container:
            match_elements = container.find_all('div', class_='cb-mtch-lst')

            for match_element in match_elements:
                try:
                    desc_tag = match_element.find('a', class_='text-hvr-underline')
                    if not desc_tag:
                        continue

                    title = desc_tag.text.strip()
                    if not title:
                        continue

                    href = desc_tag.get('href', '')

                    # Extract match ID
                    match_id_match = re.search(r'/(\d+)', href)
                    if not match_id_match:
                        continue

                    match_id = match_id_match.group(1)

                    # Get status if available
                    status_elem = match_element.find('div', class_=re.compile(r'cb-text-(live|complete)'))
                    status = status_elem.text.strip() if status_elem else 'Live'

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

@app.route('/cricket/ipl', methods=['GET'])
def get_ipl_matches():
    """Get IPL 2026 matches - uses same selectors as live matches but filtered"""
    cached = get_from_cache('ipl-matches')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info('[FETCHING] IPL 2026 matches from Cricbuzz')
        response = requests.get('https://www.cricbuzz.com/cricket-match/ipl-2026',
                              headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        matches = []

        # Use proven selectors from MCP server
        container = soup.find('div', id='page-wrapper')
        if container:
            match_elements = container.find_all('div', class_='cb-mtch-lst')

            for match_element in match_elements:
                try:
                    desc_tag = match_element.find('a', class_='text-hvr-underline')
                    if not desc_tag:
                        continue

                    title = desc_tag.text.strip()
                    if not title or 'IPL' not in title:
                        continue

                    href = desc_tag.get('href', '')

                    # Extract match ID
                    match_id_match = re.search(r'/(\d+)', href)
                    if not match_id_match:
                        continue

                    match_id = match_id_match.group(1)

                    # Get status
                    status_elem = match_element.find('div', class_=re.compile(r'cb-text-(live|complete)'))
                    status = status_elem.text.strip() if status_elem else 'Scheduled'

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
    """Get detailed match score"""
    cached = get_from_cache(f'match-{match_id}')
    if cached:
        return jsonify({**cached, 'cache': 'HIT'})

    try:
        logger.info(f'[FETCHING] Match {match_id} details')
        url = f'https://www.cricbuzz.com/live-cricket-scores/{match_id}'
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract title
        title_elem = soup.find('h1')
        title = title_elem.text.strip() if title_elem else 'Match'

        result = {
            'match_id': match_id,
            'title': title,
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
