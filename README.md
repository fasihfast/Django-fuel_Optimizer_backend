# Fuel Route Optimizer API

A Django + Django REST Framework API that, given a start and finish location
in the USA, returns:

- the driving route (as GeoJSON, ready to drop into any map viewer),
- the optimal fuel stops along the way (cheapest available price, respecting
  a 500-mile vehicle range), and
- the total fuel cost for the whole trip, assuming 10 miles/gallon.

## How it works

```
POST /api/route/  {"start": "...", "finish": "..."}
        │
        ├─ 1. Geocode start   (Nominatim - free, no API key)
        ├─ 2. Geocode finish  (Nominatim)
        ├─ 3. Get driving route (OSRM - free, no API key)   ← 3 external calls total
        │
        ├─ Look up nearby fuel stations from our OWN database
        │  (pre-geocoded once, offline - zero extra external calls)
        │
        ├─ Greedy "cheapest reachable station" algorithm
        │  picks where to refuel, respecting the 500-mile range
        │
        └─ Response: route geometry + fuel stops + total cost
```

Only **3 calls** to free external APIs are made per request (2 geocodes + 1
route), which is within the assessment's "one call ideal, two or three
acceptable" budget. The ~8,000-row fuel price CSV is geocoded **once**,
offline, by a management command - not on every request.

## Key assumptions (Important)

1. The vehicle starts the trip with a full tank, so the first 500 miles
   never cost anything - only actual refueling stops are charged.
2. At each fuel stop, the vehicle buys exactly enough gas to reach the next
   planned stop (or the destination), not a full tank. This is at least as
   cheap as always topping off, and keeps the cost math simple and exact.
3. A fuel station "counts" as being on the route if it's within ~4 miles of
   the route line (roughly a highway-exit distance). This is configurable
   (`corridor_miles` in `find_stations_near_route`).
4. If a stretch of route has no fuel station within 500 miles, the API
   returns a `422` explaining the trip isn't feasible with that range.

## Project layout

```
fuel_route_project/       Django project settings/urls 
routing/                  The one Django "app" 
  models.py               FuelStation table
  views.py                The REST endpoint 
  serializers.py          Request validation 
  services/
    geocode.py             Nominatim client
    routing_client.py       OSRM client
    fuel_optimizer.py        The actual route-math / greedy algorithm 
  management/commands/
    load_fuel_stations.py   One-time data loader + geocoder
data/fuel-prices.csv       The provided dataset
```

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate

# Quick smoke test with a small slice of the data (~5 min):
python manage.py load_fuel_stations --limit 300

# Full load before your final demo (~70-90 min, one time only,
# resumable if interrupted - just run it again):
python manage.py load_fuel_stations

python manage.py runserver
```

The API is now at `http://127.0.0.1:8000/api/route/`.

## Example request

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "Denver, CO"}'
```

## Possible future improvements

- Swap the O(stations × route points) numpy distance matrix for a spatial
  index (e.g. a KD-tree via `scipy.spatial.cKDTree`) if the dataset grew
  much larger than ~8,000 stations.
- Cache geocoding results for repeated start/finish queries (e.g. Django's
  cache framework) to shave off two of the three external calls on repeat
  requests.
- Swap SQLite for Postgres + PostGIS for real geospatial queries instead of
  the haversine-in-numpy approach used here.
