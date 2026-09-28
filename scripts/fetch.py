"""Collecte les avions autour de Guiche pour la carte GitHub Pages."""
import json
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LAT, LON = 43.5128, -1.2028
RADIUS_KM = 30
PASSAGE_GAP_SECONDS = 30 * 60
HEADERS = {'User-Agent': 'RadarGuiche/1.1 (personal hobby project)'}

def get_json(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
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

for plane in aircraft:
    key = str(plane.get('hex') or '').strip().lower()
    if not key or plane.get('lat') is None or plane.get('lon') is None:
        continue
    try:
        if distance_km(float(plane['lat']), float(plane['lon'])) > RADIUS_KM: continue
    except (TypeError, ValueError):
        continue
    item = history.setdefault(key, {'hex': key, 'passages': []})
    if plane.get('dbFlags') is not None:
        try: item['category'] = 'militaire' if int(plane['dbFlags']) & 1 else 'civil_presume'
        except (ValueError, TypeError): pass
    for field in ('r', 'flight', 't'):
        if plane.get(field): item[field] = str(plane[field]).strip()
    visits = item['passages']
    if visits and (stamp - datetime.fromisoformat(visits[-1]['last_seen'])).total_seconds() <= PASSAGE_GAP_SECONDS:
        visits[-1]['last_seen'] = stamp.isoformat()
    else:
        visits.append({'first_seen': stamp.isoformat(), 'last_seen': stamp.isoformat()})

root.joinpath('data.json').write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
history_path.write_text(json.dumps(history, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
print(f'{len(aircraft)} avions via {name}')
