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

    try:
        response = requests.get(
            "https://api.openrouteservice.org/v2/directions/driving-car",
            params={
                "api_key": ors_api_key,
                "start": start,
                "end": end,
            },
            headers={
                "Authorization": ors_api_key,
            },
            timeout=5,
        )
        if response.status_code != 200:
            return None

        data = response.json()

        summary = None
        if "features" in data and len(data["features"]) > 0:
            summary = data["features"][0].get("properties", {}).get("summary", {})
        elif "routes" in data and len(data["routes"]) > 0:
            summary = data["routes"][0].get("summary", {})

        if not summary:
            return None

        distance_m = summary.get("distance")
        duration_s = summary.get("duration")

        if distance_m is None or duration_s is None:
            return None

        distance_km = round(distance_m / 1000.0, 1)
        duration_minutes = round(duration_s / 60.0)

        return distance_km, duration_minutes
    except Exception:
        return None
