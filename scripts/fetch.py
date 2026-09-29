"""Collecte tout ce qui vole autour de Guiche pour la carte GitHub Pages."""
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
STALE_POSITION_SECONDS = 300   # on garde une dernière position connue de moins de 5 min
MAX_AIRCRAFT_LOOKUPS = 25      # fiches appareil adsbdb interrogées au maximum par exécution
HEADERS = {'User-Agent': 'RadarGuiche/1.2 (personal hobby project)'}

# Catégorie d'émetteur ADS-B -> genre (A = aéronefs, B = autres engins volants, C = sol).
KIND_BY_EMITTER = {
    'A1': 'avion_leger', 'A2': 'avion', 'A3': 'avion', 'A4': 'avion', 'A5': 'avion',
    'A6': 'chasse', 'A7': 'helicoptere', 'B1': 'planeur', 'B2': 'ballon',
    'B3': 'parachutiste', 'B4': 'ulm', 'B6': 'drone', 'B7': 'spatial',
}
# Champ "category" d'OpenSky (avec extended=1) -> catégorie d'émetteur ADS-B.
OPENSKY_EMITTER = {
    2: 'A1', 3: 'A2', 4: 'A3', 5: 'A4', 6: 'A5', 7: 'A6', 8: 'A7', 9: 'B1', 10: 'B2',
    11: 'B3', 12: 'B4', 14: 'B6', 15: 'B7', 16: 'C1', 17: 'C2', 18: 'C3', 19: 'C4', 20: 'C5',
}
# Codes type OACI d'hélicoptères courants (secours lorsque la catégorie n'est pas émise).
HELI_TYPES = {
    'EC20', 'EC25', 'EC30', 'EC35', 'EC45', 'EC55', 'EC75', 'H160', 'BK17', 'AS50', 'AS55',
    'AS65', 'AS32', 'AS3B', 'ALO2', 'ALO3', 'LAMA', 'GAZL', 'PUMA', 'NH90', 'TIGR', 'EH10',
    'G2CA', 'A109', 'A119', 'A129', 'A139', 'A149', 'A169', 'A189', 'B06', 'B06T', 'B47G',
    'B407', 'B412', 'B429', 'B505', 'R22', 'R44', 'R66', 'S76', 'S92', 'H60', 'H64', 'UH1',
    'H500', 'EXPL', 'EN28', 'EN48',
}


def get_json(url, timeout=20):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def kind_of(plane):
    emitter = str(plane.get('category') or '').upper()
    type_code = str(plane.get('t') or '').upper()
    text = f"{plane.get('desc') or ''} {plane.get('model') or ''}".upper()
    if emitter == 'A7' or type_code in HELI_TYPES or 'COPTER' in text or 'HELI' in text:
        return 'helicoptere'
    return KIND_BY_EMITTER.get(emitter)


def is_surface(plane):
    # Véhicules d'aéroport et obstacles : ils ne volent pas.
    return str(plane.get('category') or '').upper().startswith('C')


def normalize(plane):
    """Récupère une position récente si l'appareil l'a perdue un instant, et déduit son genre."""
    if plane.get('lat') is None or plane.get('lon') is None:
        last = plane.get('lastPosition')
        if (isinstance(last, dict) and last.get('lat') is not None and last.get('lon') is not None
                and (last.get('seen_pos') or 0) <= STALE_POSITION_SECONDS):
            plane['lat'], plane['lon'] = last['lat'], last['lon']
            plane['pos_stale'] = True
    plane.pop('lastPosition', None)
    kind = kind_of(plane)
    if kind:
        plane['kind'] = kind
    return plane


def adsb():
    data = get_json(f'https://api.adsb.lol/v2/point/{LAT}/{LON}/55')
    if not isinstance(data.get('ac'), list):
        raise ValueError('Format ADSB.lol inattendu')
    fields = ('hex', 'flight', 'r', 't', 'desc', 'ownOp', 'category', 'type', 'lat', 'lon',
              'lastPosition', 'alt_baro', 'alt_geom', 'gs', 'track', 'dbFlags')
    return data.get('now'), [{k: a[k] for k in fields if k in a} for a in data['ac'] if isinstance(a, dict)]


def opensky():
    # Boîte de 2,6° couvrant largement le rayon maximal de la carte ; extended=1 ajoute la catégorie.
    url = 'https://opensky-network.org/api/states/all?lamin=42.2&lomin=-2.6&lamax=44.8&lomax=0.2&extended=1'
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
        if s[8]: a['alt_baro'] = 'ground'
        if s[9] is not None: a['gs'] = round(s[9] / 0.514444, 1)
        if s[10] is not None: a['track'] = s[10]
        if len(s) > 17 and s[17] in OPENSKY_EMITTER: a['category'] = OPENSKY_EMITTER[s[17]]
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

aircraft = [normalize(a) for a in aircraft if not is_surface(a)]

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


def lookup_aircraft(hex_code):
    """Fiche de l'appareil (propriétaire, modèle). None = à retenter, {} = inconnu d'adsbdb."""
    try:
        data = get_json('https://api.adsbdb.com/v0/aircraft/' + quote(hex_code), timeout=6)
    except urllib.error.HTTPError as exc:
        return {} if exc.code == 404 else None
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    response = data.get('response') if isinstance(data, dict) else None
    ac = response.get('aircraft') if isinstance(response, dict) else None
    if not isinstance(ac, dict):
        return {}
    model = ' '.join(x for x in (str(ac.get('manufacturer') or '').strip(), str(ac.get('type') or '').strip()) if x)
    return {
        'owner': str(ac.get('registered_owner') or '').strip() or None,
        'model': model or None,
        'icao_type': str(ac.get('icao_type') or '').strip() or None,
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

# Fiche appareil demandée une seule fois par appareil (utile surtout pour les hélicoptères,
# qui n'ont presque jamais de compagnie ni de trajet).
to_lookup = []
for plane in nearby:
    key = str(plane.get('hex') or '').strip().lower()
    if key and not history.get(key, {}).get('aircraft_checked') and key not in to_lookup:
        to_lookup.append(key)
to_lookup = to_lookup[:MAX_AIRCRAFT_LOOKUPS]

with ThreadPoolExecutor(max_workers=6) as pool:
    known_routes.update(zip(missing, pool.map(lookup_route, missing)))
    aircraft_info = dict(zip(to_lookup, pool.map(lookup_aircraft, to_lookup)))

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
    info = aircraft_info.get(key)
    if info is not None:
        item['aircraft_checked'] = True
        for field in ('owner', 'model'):
            if info.get(field): item[field] = info[field]
        if info.get('icao_type') and not plane.get('t'): plane['t'] = info['icao_type']
    if plane.get('ownOp') and not item.get('owner'):
        item['owner'] = str(plane['ownOp']).strip()
    for field in ('r', 'flight', 't', 'desc'):
        if plane.get(field): item[field] = str(plane[field]).strip()
    # "category" de l'appareil (émetteur ADS-B) prime sur le statut militaire/civil de l'historique.
    kind = kind_of({**item, **plane})
    if kind:
        item['kind'] = kind
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
helis = sum(1 for a in nearby if history.get(str(a['hex']).lower(), {}).get('kind') == 'helicoptere')
print(f'{len(aircraft)} aéronefs via {name} · {len(nearby)} dans {RADIUS_KM} km dont {helis} hélicoptère(s)')
