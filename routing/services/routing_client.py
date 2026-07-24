"""
Thin wrapper around the free OSRM (Open Source Routing Machine) public
demo server. No API key required.

Docs: http://project-osrm.org/docs/v5.24.0/api/#route-service

We ask for `overview=full` + `geometries=geojson` so we get back the
full route line (a list of [lon, lat] points) in a single call - this
is the ONE call to the map/routing API that the assessment asks us to
keep to a minimum.
"""
import requests
from django.conf import settings


class RoutingError(Exception):
    """Raised when OSRM can't compute a route between the two points."""


def get_driving_route(start_lat, start_lon, finish_lat, finish_lon) -> dict:
    """
    Returns:
        {
            "distance_miles": float,
            "duration_seconds": float,
            "geometry": [[lat, lon], [lat, lon], ...]   # note: lat/lon order,
                                                          # flipped from OSRM's
                                                          # native lon/lat for
                                                          # convenience.
        }
    """
    # OSRM expects "lon,lat;lon,lat" in the URL path.
    coordinates = f"{start_lon},{start_lat};{finish_lon},{finish_lat}"
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{coordinates}"

    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "false",
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    payload = response.json()

    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RoutingError(f"OSRM could not find a route: {payload.get('message', payload.get('code'))}")

    route = payload["routes"][0]
    meters = route["distance"]
    seconds = route["duration"]
    # GeoJSON coordinates are [lon, lat] - flip to [lat, lon] for our API.
    coords_lonlat = route["geometry"]["coordinates"]
    coords_latlon = [[lat, lon] for lon, lat in coords_lonlat]

    return {
        "distance_miles": meters / 1609.344,
        "duration_seconds": seconds,
        "geometry": coords_latlon,
    }
