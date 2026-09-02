from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

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
