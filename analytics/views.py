from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils.translation import gettext as _

from .services import DEFAULT_PERIOD, PERIOD_CHOICES, build_dashboard


@login_required
def dashboard(request):
    """REQ-30: analytics dashboard for the team (staff only)."""
    if not request.user.is_staff:
        raise PermissionDenied(_("Only admin users can see the analytics."))
    try:
        period = int(request.GET.get("days", DEFAULT_PERIOD))
    except ValueError:
        period = DEFAULT_PERIOD
    if period not in PERIOD_CHOICES:
        period = DEFAULT_PERIOD

    context = build_dashboard(period)
    context["period_choices"] = PERIOD_CHOICES
    return render(request, "analytics/dashboard.html", context)
