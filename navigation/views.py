import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from events.models import Event

from .forms import AccommodationForm


@login_required
def accommodation_edit(request):
    """REQ-01: capture the user's accommodation address/coordinates."""
    accommodation = getattr(request.user, "accommodation", None)

    if request.method == "POST":
        form = AccommodationForm(request.POST, instance=accommodation)
        if form.is_valid():
            accommodation = form.save(commit=False)
            accommodation.user = request.user
            accommodation.save()
            return redirect("events:event_list")
    else:
        form = AccommodationForm(instance=accommodation)

    return render(request, "navigation/accommodation_form.html", {"form": form})


def event_map(request):
    """REQ-09: interactive map with every upcoming event that has coordinates.
    REQ-10: clicking a marker previews the event (title, category, date,
    price) with a link to its detail page. Needs GOOGLE_MAPS_API_KEY with the
    Maps JavaScript API enabled — without it we show a setup message instead
    of a blank/broken map."""
    events = (
        Event.objects.select_related("category")
        .exclude(latitude__isnull=True)
        .exclude(longitude__isnull=True)
    )
    events_without_coords = Event.objects.filter(latitude__isnull=True).count()

    markers = [
        {
            "id": event.pk,
            "title": event.title,
            "category": event.category.name if event.category else "General",
            "date": event.date_time.strftime("%d %b %Y — %H:%M"),
            "price": "Free" if event.is_free else (f"${event.price}" if event.price is not None else "N/A"),
            "lat": float(event.latitude),
            "lng": float(event.longitude),
            "url": reverse("events:event_detail", args=[event.pk]),
        }
        for event in events
    ]

    return render(
        request,
        "navigation/map.html",
        {
            "google_maps_js_key": settings.GOOGLE_MAPS_API_KEY,
            "markers_json": json.dumps(markers),
            "events_without_coords": events_without_coords,
        },
    )
