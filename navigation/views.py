from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from events.models import Event
from search.forms import EventFilterForm
from search.services import filter_events

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
    """REQ-09/REQ-10: interactive map of the *filtered* events.

    Reuses the Search component (EventFilterForm + filter_events) so the map
    shows exactly the events the catalog would list for the same querystring.
    """
    filter_form = EventFilterForm(request.GET or None)

    # REQ-08/REQ-14: the radius and the proximity order are measured from the
    # user's accommodation (REQ-01), exactly as in the event list.
    accommodation = (
        getattr(request.user, "accommodation", None) if request.user.is_authenticated else None
    )
    origin = (accommodation.latitude, accommodation.longitude) if accommodation else None

    # With an origin filter_events returns a list (distances are computed in
    # Python); without one it returns a queryset. list() covers both.
    filtered = list(
        filter_events(Event.objects.select_related("category"), filter_form, origin=origin)
    )
    events = [e for e in filtered if e.latitude is not None and e.longitude is not None]
    events_without_coords = len(filtered) - len(events)
    markers = [
        {
            "id": e.pk,
            "title": e.title,
            "category": e.category.name if e.category else "General",
            "date": timezone.localtime(e.date_time).strftime("%d %b %Y — %H:%M"),
            "price": "Free" if e.is_free else (f"${e.price}" if e.price is not None else "N/A"),
            "lat": float(e.latitude),
            "lng": float(e.longitude),
            "url": reverse("events:event_detail", args=[e.pk]),
        }
        for e in events
    ]
    return render(
        request,
        "navigation/map.html",
        {
            "google_maps_js_key": settings.GOOGLE_MAPS_API_KEY,
            "markers": markers,
            "events_without_coords": events_without_coords,
            "filter_form": filter_form,
            "accommodation": accommodation,
        },
    )
