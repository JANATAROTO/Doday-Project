from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from navigation.services import get_transit_route
from search.forms import EventFilterForm
from search.services import filter_events

from .forms import EventForm, SignupForm
from .models import Event


def _get_favorite_ids(request):
    """REQ-16: favorites are stored in the session (no dedicated model) but
    only for authenticated users — guests must log in to save favorites."""
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

    # REQ-08: the radius is measured from the user's accommodation, so the
    # filter is only available once they have saved one (REQ-01).
    accommodation = (
        getattr(request.user, "accommodation", None) if request.user.is_authenticated else None
    )
    origin = (accommodation.latitude, accommodation.longitude) if accommodation else None

    filter_form = EventFilterForm(request.GET or None)
    events = filter_events(events, filter_form, origin=origin)

    return render(
        request,
        "events/event_list.html",
        {
            "events": events,
            "filter_form": filter_form,
            "accommodation": accommodation,
        },
    )


def event_detail(request, pk):
    event = get_object_or_404(Event.objects.select_related("category"), pk=pk)

    # REQ-15: External navigation link to Google Maps
    google_maps_url = event.google_maps_url

    # REQ-03: transit estimate via ORS. Only calculate if authenticated & accommodation exists.
    transit_route = None
    accommodation = getattr(request.user, "accommodation", None) if request.user.is_authenticated else None
    if accommodation and event.latitude is not None and event.longitude is not None:
        transit_route = get_transit_route(
            accommodation.latitude, accommodation.longitude, event.latitude, event.longitude
        )

    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "accommodation": accommodation,
            "transit_estimate": transit_route,
            "transit_route": transit_route,
            "distance_km": transit_route["distance_km"] if transit_route else None,
            "duration_minutes": transit_route["duration_minutes"] if transit_route else None,
            "google_maps_url": google_maps_url,
            "is_favorited": event.pk in _get_favorite_ids(request),
        },
    )


@login_required
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


@login_required
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
