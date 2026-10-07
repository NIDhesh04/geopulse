"""Download major roads of Bhubaneswar from Overpass API."""
import json
import requests
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import PROJECT_ROOT

EXT_DIR = PROJECT_ROOT / "data" / "external"
EXT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = EXT_DIR / "bhubaneswar_major_osm.json"

bbox = (20.21, 85.78, 20.37, 85.89)
q = f"""[out:json][timeout:90];
(
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link)$"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
);
out body;
>;
out skel qt;
"""

headers = {"User-Agent": "GeopulseTrafficResearch/1.0 (academic research; contact: research@geopulse.bhu)"}
endpoints = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter"
]

success = False
for url in endpoints:
    try:
        print(f"Querying {url}...")
        r = requests.post(url, data={"data": q}, headers=headers, timeout=90)
        if r.status_code == 200:
            data = r.json()
            el = data.get("elements", [])
            print(f"Success! {url} returned {len(el)} elements.")
            OUT_FILE.write_text(json.dumps(data), encoding="utf-8")
            success = True
            break
        else:
            print(f"{url} returned status: {r.status_code}")
    except Exception as e:
        print(f"{url} error: {e}")

if not success:
    print("Failed to download major road network from Overpass.")
    sys.exit(1)
