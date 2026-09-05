from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from navigation.services import estimate_transit
from search.forms import EventFilterForm
from search.services import filter_events

from .forms import EventForm, SignupForm
from .models import Event


def _get_favorite_ids(request):
    """REQ-16: favorites are stored in the session so both guests and
    authenticated users can bookmark events without a dedicated model."""
    return request.session.get("favorite_ids", [])


def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect("events:event_list")
    else:
        form = SignupForm()

    return render(request, "registration/signup.html", {"form": form})


def event_list(request):
    """REQ-02: list events. Filtering (REQ-07/11/19/20/22) is delegated to
    the Search component so this view only owns display concerns."""
    events = Event.objects.select_related("category").all()

    filter_form = EventFilterForm(request.GET or None)
    events = filter_events(events, filter_form)

    return render(
        request, "events/event_list.html", {"events": events, "filter_form": filter_form}
    )


def event_detail(request, pk):
    event = get_object_or_404(Event.objects.select_related("category"), pk=pk)

    # REQ-21: external ticketing link. Every event points to the same
    # platform for now — no per-organizer ticketing integration yet.
    ticket_url = "https://www.ticketmaster.co/"

    # REQ-15: External navigation link to Google Maps
    google_maps_url = event.google_maps_url

    # REQ-03: transit estimate via ORS. Only calculate if authenticated & accommodation exists.
    transit_estimate = None
    accommodation = getattr(request.user, "accommodation", None) if request.user.is_authenticated else None
    if accommodation and event.latitude is not None and event.longitude is not None:
        try:
            result = estimate_transit(
                accommodation.latitude, accommodation.longitude, event.latitude, event.longitude
            )
            if result:
                distance_km, duration_minutes = result
                transit_estimate = {"distance_km": distance_km, "duration_minutes": duration_minutes}
        except Exception:
            transit_estimate = None

    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "accommodation": accommodation,
            "transit_estimate": transit_estimate,
            "distance_km": transit_estimate["distance_km"] if transit_estimate else None,
            "duration_minutes": transit_estimate["duration_minutes"] if transit_estimate else None,
            "google_maps_url": google_maps_url,
            "ticket_url": ticket_url,
            "is_favorited": event.pk in _get_favorite_ids(request),
        },
    )


@require_POST
def favorite_toggle(request, pk):
    """REQ-16: bookmark/unbookmark an event into the session's favorites list."""
    event = get_object_or_404(Event, pk=pk)
    favorite_ids = _get_favorite_ids(request)

    if event.pk in favorite_ids:
        favorite_ids.remove(event.pk)
    else:
        favorite_ids.append(event.pk)
    request.session["favorite_ids"] = favorite_ids

    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("events:event_detail", pk=event.pk)


def favorites_list(request):
    """REQ-17: dedicated panel listing the session's saved favorite events."""
    favorite_ids = _get_favorite_ids(request)
    events = Event.objects.select_related("category").filter(pk__in=favorite_ids)
    return render(request, "events/favorites_list.html", {"events": events})


@login_required
def event_create(request):
    """REQ-04: create events (admin/organizer only)."""
    if not request.user.is_staff:
        raise PermissionDenied("Only admin users can create events.")

    if request.method == "POST":
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.organizer = request.user
            event.save()
            return redirect("events:event_detail", pk=event.pk)
    else:
        form = EventForm()

    return render(request, "events/event_form.html", {"form": form, "event": None})


@login_required
def event_edit(request, pk):
    """REQ-05: edit events (only the organizer who created it)."""
    event = get_object_or_404(Event, pk=pk)
    if not request.user.is_staff or event.organizer_id != request.user.id:
        raise PermissionDenied("Only the admin user who organizes this event can edit it.")

    if request.method == "POST":
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            return redirect("events:event_detail", pk=event.pk)
    else:
        form = EventForm(instance=event)

    return render(request, "events/event_form.html", {"form": form, "event": event})


@login_required
def event_delete(request, pk):
    """REQ-06: delete events (only the organizer who created it)."""
    event = get_object_or_404(Event, pk=pk)
    if not request.user.is_staff or event.organizer_id != request.user.id:
        raise PermissionDenied("Only the admin user who organizes this event can delete it.")

    if request.method == "POST":
        event.delete()
        return redirect("events:event_list")

    return render(request, "events/event_confirm_delete.html", {"event": event})
