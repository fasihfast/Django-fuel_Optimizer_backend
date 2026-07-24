"""
The actual "business logic" of this assessment:

1. Given the route geometry (a list of lat/lon points from OSRM), figure
   out how far along the route each point is (cumulative miles).
2. Find which fuel stations lie close enough to the route to be usable
   ("corridor" filtering using the haversine distance from each station
   to its nearest point on the route).
3. Walk the route and greedily pick the cheapest reachable fuel station
   every time the vehicle would otherwise run out of range, the classic
   "gas station" greedy strategy.
4. Work out exactly how many gallons were bought at each stop and what
   it cost.


"""
import math

import numpy as np

EARTH_RADIUS_MILES = 3958.8


class RouteInfeasibleError(Exception):
    """Raised when the trip cannot be completed with the given vehicle range."""


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points, in miles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def build_route_points(geometry, max_points=600):
    """
    geometry: list of [lat, lon] pairs as returned by our routing client.
    Downsamples long routes (OSRM can return thousands of points) so the
    later distance-matrix math stays fast, then computes the cumulative
    distance travelled (in miles) at each remaining point.

    Returns: list of (lat, lon, cumulative_miles) tuples.
    """
    n = len(geometry)
    if n > max_points:
        step = math.ceil(n / max_points)
        sampled = geometry[::step]
        if sampled[-1] != geometry[-1]:
            sampled = sampled + [geometry[-1]]
    else:
        sampled = geometry

    points = []
    cumulative = 0.0
    prev = None
    for lat, lon in sampled:
        if prev is not None:
            cumulative += haversine_miles(prev[0], prev[1], lat, lon)
        points.append((lat, lon, cumulative))
        prev = (lat, lon)
    return points


def find_stations_near_route(route_points, stations, corridor_miles=4.0):
    """
    route_points: output of build_route_points()
    stations: iterable of FuelStation model instances (with lat/lon set)
    corridor_miles: how far off the route a station may be and still count
                     as "on the way" (rough highway-exit distance)

    Uses one vectorized numpy distance matrix (stations x route_points)
    instead of a nested Python loop, so this comfortably handles the
    full ~8,000 row fuel price dataset in well under a second.

    Returns: list of dicts:
        {"station": FuelStation, "position_miles": float, "distance_from_route_miles": float}
    """
    stations = [s for s in stations if s.latitude is not None and s.longitude is not None]
    if not stations or not route_points:
        return []

    route_lat = np.radians(np.array([p[0] for p in route_points]))
    route_lon = np.radians(np.array([p[1] for p in route_points]))
    cumulative = np.array([p[2] for p in route_points])

    station_lat = np.radians(np.array([s.latitude for s in stations]))
    station_lon = np.radians(np.array([s.longitude for s in stations]))

    # Broadcast into an (M stations x N route points) matrix in one shot.
    dphi = route_lat[None, :] - station_lat[:, None]
    dlambda = route_lon[None, :] - station_lon[:, None]
    a = (
        np.sin(dphi / 2) ** 2
        + np.cos(station_lat[:, None]) * np.cos(route_lat[None, :]) * np.sin(dlambda / 2) ** 2
    )
    dist_matrix = 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0, 1)))

    nearest_idx = np.argmin(dist_matrix, axis=1)
    nearest_dist = dist_matrix[np.arange(len(stations)), nearest_idx]

    results = []
    for i, station in enumerate(stations):
        if nearest_dist[i] <= corridor_miles:
            results.append(
                {
                    "station": station,
                    "position_miles": float(cumulative[nearest_idx[i]]),
                    "distance_from_route_miles": float(nearest_dist[i]),
                }
            )
    return results


def plan_fuel_stops(total_distance_miles, candidates, max_range_miles=500, mpg=10):
    """
    Greedily choose where to refuel and work out the total cost.

    Assumptions (call these out explicitly in the README / demo video):
      - The vehicle starts with a full tank (first 500 miles are "free" -
        already paid for before the trip started).
      - At each stop, we buy exactly the gallons needed to reach the next
        planned stop (or the destination) rather than always filling the
        tank - this never costs more than filling up, and is cheaper
        whenever a lower price shows up later while there's still room
        in the tank.
      - Strategy: at every point where the destination is out of reach on
        the current tank, look at every station reachable within the next
        500 miles and refuel at the cheapest one. This is the standard
        greedy solution to the "minimum cost refueling" problem.

    candidates: output of find_stations_near_route(), each dict additionally
                needs a "price" key (float).
    Returns: (stops: list[dict], total_cost: float)
    Raises: RouteInfeasibleError if a gap between fuel stations is too
            large to bridge with a full tank.
    """
    candidates = sorted(candidates, key=lambda c: c["position_miles"])

    if total_distance_miles <= max_range_miles:
        return [], 0.0

    chosen_stops = []
    current_pos = 0.0

    while total_distance_miles - current_pos > max_range_miles:
        reachable = [
            c for c in candidates
            if current_pos < c["position_miles"] <= current_pos + max_range_miles
        ]
        if not reachable:
            raise RouteInfeasibleError(
                f"No fuel station found within {max_range_miles} miles of mile "
                f"{current_pos:.1f} along the route - this trip can't be "
                f"completed with a {max_range_miles}-mile range."
            )
        # Cheapest first; if tied on price, prefer the farther one so we
        # need fewer total stops.
        chosen = min(reachable, key=lambda c: (c["price"], -c["position_miles"]))
        chosen_stops.append(chosen)
        current_pos = chosen["position_miles"]

    # Second pass: now that we know the stop order, work out gallons/cost
    # per leg. Leg i runs from chosen_stops[i] to chosen_stops[i+1] (or the
    # destination for the last one), and is paid for at chosen_stops[i]'s price.
    stop_details = []
    total_cost = 0.0
    for i, stop in enumerate(chosen_stops):
        next_position = (
            chosen_stops[i + 1]["position_miles"] if i + 1 < len(chosen_stops) else total_distance_miles
        )
        leg_distance = next_position - stop["position_miles"]
        gallons = leg_distance / mpg
        price = float(stop["price"])
        cost = gallons * price
        total_cost += cost
        stop_details.append(
            {
                **stop,
                "gallons_purchased": round(gallons, 3),
                "cost_for_this_fill": round(cost, 2),
            }
        )

    return stop_details, round(total_cost, 2)
