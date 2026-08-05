"""Estimacion de distancia y tiempo de viaje entre el alojamiento y un evento."""

import requests
from django.conf import settings


def estimate_transit(origin_lat, origin_lon, dest_lat, dest_lon):
    """Devuelve (distancia_km, minutos) usando Google Distance Matrix API.

    Devuelve None si todavia no hay API key configurada (GOOGLE_MAPS_API_KEY
    vacio) o si la llamada a la API falla.
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