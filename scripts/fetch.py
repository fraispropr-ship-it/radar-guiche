"""Sauvegarde un instantané public des positions près de Guiche."""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = 'https://api.airplanes.live/v2/point/43.5128/-1.2028/55'
request = urllib.request.Request(URL, headers={'User-Agent': 'RadarGuiche/1.0 (personal hobby project)'})
with urllib.request.urlopen(request, timeout=20) as response:
    data = json.load(response)
if not isinstance(data.get('ac'), list):
    raise ValueError('Réponse API invalide : ac absent')
# Ne conserver que les champs affichés ; l'historique n'est pas stocké.
fields = ('hex', 'flight', 'r', 't', 'lat', 'lon', 'alt_baro', 'alt_geom', 'gs', 'track')
aircraft = [{key: item[key] for key in fields if key in item} for item in data['ac'] if isinstance(item, dict)]
output = {'now': data.get('now', datetime.now(timezone.utc).timestamp()), 'fetched_at': datetime.now(timezone.utc).isoformat(), 'ac': aircraft}
Path(__file__).resolve().parents[1].joinpath('data.json').write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
print(f'{len(aircraft)} appareils sauvegardés')
