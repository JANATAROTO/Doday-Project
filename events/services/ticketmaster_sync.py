"""REQ-13: Ticketmaster Discovery API sync service.

Pure module — no Django views, no HTTP request handling, no side-effects
beyond DB writes.  Designed to be tested with mocks in the same way that
navigation/services.py is tested.

Usage (e.g. from a management command or a scheduled task):
    from events.services.ticketmaster_sync import sync_ticketmaster_events
    created, updated = sync_ticketmaster_events()
"""
import os

import requests
from django.conf import settings

from events.models import Category, Event


# ---------------------------------------------------------------------------
# Low-level: talk to the external API
# ---------------------------------------------------------------------------

def fetch_ticketmaster_events(city="Medellín", size=50):
    """Return a list of raw event dicts from the Ticketmaster Discovery API.

    Returns an empty list when:
    - TICKETMASTER_API_KEY is not configured, or
    - the HTTP call fails / times out / returns a non-200 status.

    This mirrors the "return None / []" defensive pattern used in
    navigation/services.py so callers never need to guard against exceptions.
    """
    api_key = (
        getattr(settings, "TICKETMASTER_API_KEY", "")
        or os.environ.get("TICKETMASTER_API_KEY", "")
    )
    if not api_key:
        return []

    try:
        response = requests.get(
            "https://app.ticketmaster.com/discovery/v2/events.json",
            params={"apikey": api_key, "city": city, "size": size},
            timeout=10,
        )
        if response.status_code != 200:
            return []
        return response.json().get("_embedded", {}).get("events", [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# High-level: upsert raw events into the DB
# ---------------------------------------------------------------------------

def sync_ticketmaster_events(city="Medellín", size=50):
    """Fetch Ticketmaster events and upsert them into the local Event table.

    Uses ``update_or_create`` keyed on (external_source, external_id) so
    running this multiple times is idempotent — same pattern as seed_events.py.

    Returns:
        (created: int, updated: int)  — counts of new vs refreshed records.
    """
    raw_events = fetch_ticketmaster_events(city=city, size=size)
    created_count = 0
    updated_count = 0

    for raw in raw_events:
        # --- category ---------------------------------------------------------
        segment_name = (
            raw.get("classifications", [{}])[0]
            .get("segment", {})
            .get("name", "General")
        )
        category, _ = Category.objects.get_or_create(name=segment_name)

        # --- venue / location -------------------------------------------------
        venue = raw.get("_embedded", {}).get("venues", [{}])[0]
        location_data = venue.get("location", {})

        # Ticketmaster may omit dateTime for day-only events; skip those.
        start_datetime = raw.get("dates", {}).get("start", {}).get("dateTime")
        if not start_datetime:
            continue

        # --- upsert -----------------------------------------------------------
        _, was_created = Event.objects.update_or_create(
            external_source="ticketmaster",
            external_id=raw["id"],
            defaults={
                "title": raw.get("name", ""),
                "description": raw.get("info", "") or raw.get("pleaseNote", "") or "",
                "date_time": start_datetime,
                "location": venue.get("name", ""),
                "latitude": location_data.get("latitude") or None,
                "longitude": location_data.get("longitude") or None,
                "category": category,
                "is_free": False,
                "ticket_url": raw.get("url", ""),
            },
        )

        if was_created:
            created_count += 1
        else:
            updated_count += 1

    return created_count, updated_count
