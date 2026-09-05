from django import forms

from events.models import Category


class EventFilterForm(forms.Form):
    """Search component — filters the Events catalog without owning any table.

    REQ-19: keyword search over title/description.
    REQ-07: date-range filter (check-in/check-out).
    REQ-11: category filter.
    REQ-22: free-admission-only filter.
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
    free_only = forms.BooleanField(required=False, label="Solo gratis")

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError("The start date must be on or before the end date.")
        return cleaned_data
