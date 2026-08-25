from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Accommodation, Category, Event

User = get_user_model()


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "date_time",
            "end_date",
            "location",
            "category",
            "is_free",
            "price",
        ]
        widgets = {
            "date_time": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "end_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 5}),
        }


class EventFilterForm(forms.Form):
    """RF7: filter events by a user-specified date range (check-in/check-out).
    RF11: filter events by user-selected categories.
    RF19: filter events by keyword, matched against title/description."""

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

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError("The start date must be on or before the end date.")
        return cleaned_data


class AccommodationForm(forms.ModelForm):
    class Meta:
        model = Accommodation
        fields = ["address", "latitude", "longitude"]


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="Email")


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Used to sign in — no separate username needed.")

    class Meta:
        model = User
        fields = ("email",)

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user
