"""Collecte les avions autour de Guiche pour la carte GitHub Pages."""
import json
import math
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

LAT, LON = 43.5128, -1.2028
RADIUS_KM = 30
PASSAGE_GAP_SECONDS = 30 * 60
HEADERS = {'User-Agent': 'RadarGuiche/1.1 (personal hobby project)'}

def get_json(url, timeout=20):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)

def adsb():
    data = get_json(f'https://api.adsb.lol/v2/point/{LAT}/{LON}/55')
    if not isinstance(data.get('ac'), list):
        raise ValueError('Format ADSB.lol inattendu')
    fields = ('hex', 'flight', 'r', 't', 'lat', 'lon', 'alt_baro', 'alt_geom', 'gs', 'track', 'dbFlags')
    return data.get('now'), [{k: a[k] for k in fields if k in a} for a in data['ac'] if isinstance(a, dict)]

def opensky():
    # Boîte de 2,6° couvrant largement le rayon maximal de la carte.
    url = 'https://opensky-network.org/api/states/all?lamin=42.2&lomin=-2.6&lamax=44.8&lomax=0.2'
    data = get_json(url)
    if not isinstance(data.get('states'), list):
        raise ValueError('Format OpenSky inattendu')
    aircraft = []
    for s in data['states']:
        if s[5] is None or s[6] is None:
            continue
        a = {'hex': s[0], 'flight': (s[1] or '').strip(), 'lat': s[6], 'lon': s[5]}
        if s[7] is not None: a['alt_baro'] = round(s[7] / 0.3048)
        if s[13] is not None: a['alt_geom'] = round(s[13] / 0.3048)
        if s[9] is not None: a['gs'] = round(s[9] / 0.514444, 1)
        if s[10] is not None: a['track'] = s[10]
        aircraft.append(a)
    return data.get('time'), aircraft

errors = []
for name, source in [('ADSB.lol', adsb), ('OpenSky', opensky)]:
    try:
        now, aircraft = source()
        break
    except Exception as exc:
        errors.append(f'{name}: {exc}')
else:
    raise RuntimeError('Sources indisponibles : ' + ' | '.join(errors))

root = Path(__file__).resolve().parents[1]
stamp = datetime.now(timezone.utc)
output = {'now': now or stamp.timestamp(), 'fetched_at': stamp.isoformat(), 'source': name, 'ac': aircraft}
history_path = root / 'history.json'
try:
    history = json.loads(history_path.read_text(encoding='utf-8'))
    if not isinstance(history, dict): raise ValueError('Historique invalide')
except FileNotFoundError:
    history = {}

def distance_km(lat, lon):
    a, b, c, d = map(math.radians, (LAT, LON, lat, lon))
    h = math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 12742 * math.asin(min(1, math.sqrt(h)))

def airport_info(value):
    if not isinstance(value, dict):
        return None
    name = str(value.get('name') or '').strip()
    code = str(value.get('iata_code') or value.get('icao_code') or '').strip()
    return {'name': name, 'code': code} if name or code else None

def lookup_route(callsign):
    if not re.fullmatch(r'[A-Z0-9]{3,10}', callsign):
        return None
    try:
        data = get_json('https://api.adsbdb.com/v0/callsign/' + quote(callsign), timeout=6)
        route = data.get('response', {}).get('flightroute')
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, AttributeError):
        return None
    if not isinstance(route, dict):
        return None
    airline = route.get('airline')
    return {
        'airline': str(airline.get('name') or '').strip() if isinstance(airline, dict) else None,
        'origin': airport_info(route.get('origin')),
        'destination': airport_info(route.get('destination')),
    }

nearby = []
for plane in aircraft:
    if not plane.get('hex') or plane.get('lat') is None or plane.get('lon') is None:
        continue
    try:
        if distance_km(float(plane['lat']), float(plane['lon'])) <= RADIUS_KM:
            nearby.append(plane)
    except (TypeError, ValueError):
        continue

# La route est liée à l'indicatif du vol, pas à l'appareil : un même avion
# peut effectuer un trajet différent lors de son prochain passage.
known_routes = {}
for item in history.values():
    for visit in item.get('passages', []):
        flight = visit.get('flight')
        if flight and any(visit.get(k) for k in ('airline', 'origin', 'destination')):
            known_routes[flight] = {k: visit.get(k) for k in ('airline', 'origin', 'destination')}
callsigns = {str(a.get('flight') or '').strip().upper() for a in nearby}
missing = sorted(c for c in callsigns if c and c not in known_routes)
with ThreadPoolExecutor(max_workers=6) as pool:
    known_routes.update(zip(missing, pool.map(lookup_route, missing)))

for plane in nearby:
    key = str(plane.get('hex') or '').strip().lower()
    callsign = str(plane.get('flight') or '').strip().upper()
    route = known_routes.get(callsign)
    if route:
        plane.update({k: v for k, v in route.items() if v})
    item = history.setdefault(key, {'hex': key, 'passages': []})
    if plane.get('dbFlags') is not None:
        try: item['category'] = 'militaire' if int(plane['dbFlags']) & 1 else 'civil_presume'
        except (ValueError, TypeError): pass
    for field in ('r', 'flight', 't'):
        if plane.get(field): item[field] = str(plane[field]).strip()
    visits = item['passages']
    if visits and (not callsign or not visits[-1].get('flight') or visits[-1]['flight'] == callsign) and (stamp - datetime.fromisoformat(visits[-1]['last_seen'])).total_seconds() <= PASSAGE_GAP_SECONDS:
        visit = visits[-1]
        visit['last_seen'] = stamp.isoformat()
    else:
        visit = {'first_seen': stamp.isoformat(), 'last_seen': stamp.isoformat()}
        visits.append(visit)
    if callsign:
        visit['flight'] = callsign
    if route:
        visit.update({k: v for k, v in route.items() if v})
    for field in ('airline', 'origin', 'destination'):
        if visit.get(field):
            item[field] = visit[field]
        else:
            item.pop(field, None)

root.joinpath('data.json').write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
history_path.write_text(json.dumps(history, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
print(f'{len(aircraft)} avions via {name}')
