"""
Controller File
"""
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FuelStation
from .serializers import RouteRequestSerializer
from .services.fuel_optimizer import (
    RouteInfeasibleError,
    build_route_points,
    find_stations_near_route,
    plan_fuel_stops,
)
from .services.geocode import GeocodeError, geocode_place
from .services.routing_client import RoutingError, get_driving_route


class RoutePlanView(APIView):
    """
    POST /api/route/

    Body:
        {"start": "Chicago, IL", "finish": "Denver, CO"}

    Response: route geometry (for drawing a map), the optimal fuel stops
    along the way, and the total fuel cost for the trip.

    External API calls made per request (kept to the minimum the
    assessment asks for):
        1. Geocode `start`      (OpenMeteo)
        2. Geocode `finish`     (OpenMeteo)
        3. Get driving route    (OSRM)
    Fuel station coordinates are NOT geocoded here - that happened once,
    offline, via `python manage.py load_fuel_stations` 
    """

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        start_query = serializer.validated_data["start"]
        finish_query = serializer.validated_data["finish"]

        # --- 1 & 2: geocode the two endpoints the user typed in ---------
        try:
            start_location = geocode_place(start_query)
            finish_location = geocode_place(finish_query)
        except GeocodeError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # --- 3: get the driving route between them -----------------------
        try:
            route = get_driving_route(
                start_location["latitude"],
                start_location["longitude"],
                finish_location["latitude"],
                finish_location["longitude"],
            )
        except RoutingError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        route_points = build_route_points(route["geometry"])

        # --- fuel stations: plain DB read, no external API call ----------
        # Cheap bounding-box pre-filter (with a little padding) so we're
        # not pulling every one of the ~8,000 rows out of the DB when the
        # route only spans a small part of the country.
        lats = [p[0] for p in route_points]
        lons = [p[1] for p in route_points]
        padding = 1.0  # degrees, roughly ~50-70 miles depending on latitude
        stations_qs = FuelStation.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            latitude__gte=min(lats) - padding,
            latitude__lte=max(lats) + padding,
            longitude__gte=min(lons) - padding,
            longitude__lte=max(lons) + padding,
        )

        candidates = find_stations_near_route(route_points, stations_qs, corridor_miles=4.0)
        for c in candidates:
            c["price"] = float(c["station"].retail_price)

        try:
            stops, total_cost = plan_fuel_stops(
                route["distance_miles"],
                candidates,
                max_range_miles=settings.VEHICLE_MAX_RANGE_MILES,
                mpg=settings.VEHICLE_MPG,
            )
        except RouteInfeasibleError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response(
            {
                "start": {
                    "query": start_query,
                    "resolved_address": start_location["display_name"],
                    "latitude": start_location["latitude"],
                    "longitude": start_location["longitude"],
                },
                "finish": {
                    "query": finish_query,
                    "resolved_address": finish_location["display_name"],
                    "latitude": finish_location["latitude"],
                    "longitude": finish_location["longitude"],
                },
                "vehicle": {
                    "max_range_miles": settings.VEHICLE_MAX_RANGE_MILES,
                    "mpg": settings.VEHICLE_MPG,
                },
                "total_distance_miles": round(route["distance_miles"], 1),
                "total_drive_time_hours": round(route["duration_seconds"] / 3600, 2),
                "total_fuel_cost_usd": total_cost,
                "fuel_stops": [
                    {
                        "name": s["station"].name,
                        "address": s["station"].address,
                        "city": s["station"].city,
                        "state": s["station"].state,
                        "price_per_gallon": s["price"],
                        "latitude": s["station"].latitude,
                        "longitude": s["station"].longitude,
                        "distance_along_route_miles": round(s["position_miles"], 1),
                        "gallons_purchased": s["gallons_purchased"],
                        "cost_for_this_fill_usd": s["cost_for_this_fill"],
                    }
                    for s in stops
                ],
                # GeoJSON LineString - paste this into https://geojson.io to
                # see the route on a map, or feed it straight into a
                # frontend map library (Leaflet, Mapbox GL, etc.)
                "route_map_geojson": {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "LineString",
                        # GeoJSON wants [lon, lat] order
                        "coordinates": [[lon, lat] for lat, lon, _ in route_points],
                    },
                },
            },
            status=status.HTTP_200_OK,
        )
