from decimal import Decimal

from django import forms

from events.models import Category

# REQ-14: shared with search.services, which reads the chosen value.
SORT_DATE = "date"
SORT_DISTANCE = "distance"


class EventFilterForm(forms.Form):
    """Search component — filters the Events catalog without owning any table.

    REQ-19: keyword search over title/description.
    REQ-07: date-range filter (check-in/check-out).
    REQ-11: category filter.
    REQ-22: free-admission-only filter.
    REQ-08: radius filter around the user's accommodation.
    REQ-14: sort by start date or by proximity to the accommodation.
    REQ-20: reset filters — handled by the "Clear" link in event_list.html,
    which simply reloads the page with no querystring.
    """

    q = forms.CharField(
        required=False,
        label="Keyword",
        widget=forms.TextInput(attrs={"placeholder": "Search events..."}),
    )
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    category = forms.ModelMultipleChoiceField(
        queryset=Category.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    # REQ-08: only usable once the user has saved an accommodation (REQ-01);
    # the view passes that location in as the origin. Declared before
    # free_only so the tall input is not rendered next to the checkbox, where
    # it reads as if the radius only applied to free events.
    radius_km = forms.DecimalField(
        required=False,
        min_value=Decimal("0.1"),
        max_value=Decimal("500"),
        label="Distancia máxima (km)",
        # step="any" on purpose: a stepped input rejects plain values like "3"
        # because they do not land on the step grid.
        widget=forms.NumberInput(attrs={"step": "any", "placeholder": "ej. 5"}),
    )
    free_only = forms.BooleanField(required=False, label="Solo gratis")
    # REQ-14: "sorted by physical proximity distance to the accommodation or
    # start date" — date is the default because it needs no accommodation and
    # matches Event.Meta.ordering.
    #
    # Both choices are always offered, even with no accommodation saved. It is
    # tempting to drop SORT_DISTANCE in that case, but the choices also
    # validate the querystring: a ?sort=distance bookmark would then make the
    # whole form invalid, and an invalid form applies *no* filter at all, so
    # the user's keyword and dates would be silently dropped too. Instead
    # filter_events() ignores an unusable sort and the template explains why.
    sort = forms.ChoiceField(
        required=False,
        choices=[(SORT_DATE, "Fecha"), (SORT_DISTANCE, "Distancia")],
        initial=SORT_DATE,
        label="Ordenar por",
    )

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError("The start date must be on or before the end date.")
        return cleaned_data
