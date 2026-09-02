"""Navigation component — REQ-03: estimate transit distance/time between the
user's accommodation and an event, via the Google Distance Matrix API."""
import requests
from django.conf import settings


def estimate_transit(origin_lat, origin_lon, dest_lat, dest_lon):
    """Return (distance_km, minutes) using the Google Distance Matrix API.

    Returns None if no API key is configured yet (GOOGLE_MAPS_API_KEY empty)
    or if the API call fails.
    """
    if not settings.GOOGLE_MAPS_API_KEY:
        return None

    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            params={
                "origins": f"{origin_lat},{origin_lon}",
                "destinations": f"{dest_lat},{dest_lon}",
                "mode": "transit",
                "key": settings.GOOGLE_MAPS_API_KEY,
            },
            timeout=5,
        )
        element = response.json()["rows"][0]["elements"][0]
        if element["status"] == "OK":
            distance_km = round(element["distance"]["value"] / 1000, 1)
            duration_minutes = round(element["duration"]["value"] / 60)
            return distance_km, duration_minutes
    except (requests.RequestException, KeyError, IndexError):
        pass

    return None
