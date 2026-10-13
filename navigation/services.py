"""Navigation component — REQ-03: estimate transit distance/time between the
user's accommodation and an event, via the OpenRouteService (ORS) API."""
import os
import requests
from django.conf import settings


def _format_coord(coord):
    return str(coord).replace(",", ".")


def estimate_transit(origin_lat, origin_lon, dest_lat, dest_lon):
    """Return (distance_km, duration_minutes) using OpenRouteService (ORS) API.

    Returns None if no ORS API key is configured or if the API call fails/timeouts.
    """
    ors_api_key = getattr(settings, "ORS_API_KEY", "") or os.environ.get("ORS_API_KEY", "")
    if not ors_api_key:
        return None

    # ORS critical rule: coordinates strictly in order [longitude, latitude]
    start = f"{_format_coord(origin_lon)},{_format_coord(origin_lat)}"
    end = f"{_format_coord(dest_lon)},{_format_coord(dest_lat)}"

    route = get_transit_route(origin_lat, origin_lon, dest_lat, dest_lon)
    if route is None:
        return None
    return route["distance_km"], route["duration_minutes"]


def get_transit_route(origin_lat, origin_lon, dest_lat, dest_lon):
    """Return route summary and Leaflet-ready [lat, lon] coordinates."""
    ors_api_key = getattr(settings, "ORS_API_KEY", "") or os.environ.get("ORS_API_KEY", "")
    if not ors_api_key:
        return None

    start = f"{_format_coord(origin_lon)},{_format_coord(origin_lat)}"
    end = f"{_format_coord(dest_lon)},{_format_coord(dest_lat)}"

    try:
        response = requests.get(
            "https://api.openrouteservice.org/v2/directions/driving-car",
            params={"api_key": ors_api_key, "start": start, "end": end},
            headers={"Authorization": ors_api_key},
            timeout=5,
        )
        if response.status_code != 200:
            return None

        data = response.json()
        features = data.get("features", [])
        if features:
            feature = features[0]
            summary = feature.get("properties", {}).get("summary", {})
            geometry = feature.get("geometry", {}).get("coordinates", [])
            coordinates = [[point[1], point[0]] for point in geometry if len(point) >= 2]
        else:
            routes = data.get("routes", [])
            if not routes:
                return None
            route = routes[0]
            summary = route.get("summary", {})
            coordinates = [
                [point[1], point[0]]
                for point in route.get("geometry", {}).get("coordinates", [])
                if len(point) >= 2
            ]

        if not summary:
            return None

        distance_m = summary.get("distance")
        duration_s = summary.get("duration")

        if distance_m is None or duration_s is None:
            return None

        distance_km = round(distance_m / 1000.0, 1)
        duration_minutes = round(duration_s / 60.0)

        return {
            "distance_km": distance_km,
            "duration_minutes": duration_minutes,
            "coordinates": coordinates,
        }
    except Exception:
        return None
