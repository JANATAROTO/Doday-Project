from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import Event

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
            "ticket_url",
        ]
        widgets = {
            "date_time": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "end_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 5}),
        }
        # REQ-29: user-facing labels and help, in the active language. The
        # model help_text keeps the developer notes (RF numbers) for the admin.
        labels = {
            "title": _("Title"),
            "description": _("Description"),
            "date_time": _("Start date and time"),
            "end_date": _("End date and time"),
            "location": _("Location"),
            "category": _("Category"),
            "is_free": _("Free event"),
            "price": _("Price (COP)"),
            "ticket_url": _("Ticket link"),
        }
        help_texts = {
            "date_time": "",
            "end_date": _("Only for multi-day events such as fairs or festivals."),
            "location": _("Address or place name."),
            "price": _("Leave empty if the event is free."),
            "ticket_url": _("Where attendees can buy tickets. Leave empty if there is none."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].empty_label = _("Select a category")
        self.fields["category"].label_from_instance = lambda category: category.display_name


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label=_("Email"))
    # Users log in with their email, so Django's "username and password"
    # wording would be misleading; one message, in the active language.
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("Your email and password didn't match. Please try again."),
    }


class SignupForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label=_("Email"),
        help_text=_("You will use it to log in. No username needed."),
    )

    class Meta:
        model = User
        fields = ("email",)

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class EventSubmissionForm(EventForm):
    """REQ-24: public form for local cultural managers to propose an event.

    Same event fields and labels as the staff form, plus who is proposing it,
    so a moderator can get back to them. The view saves it as pending.
    """

    class Meta(EventForm.Meta):
        fields = EventForm.Meta.fields + ["submitter_name", "submitter_email"]
        labels = {
            **EventForm.Meta.labels,
            "submitter_name": _("Your name or organization"),
            "submitter_email": _("Contact email"),
        }
        help_texts = {
            **EventForm.Meta.help_texts,
            "submitter_name": "",
            "submitter_email": _("We only use it to contact you about this proposal."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["submitter_name"].required = True
        self.fields["submitter_email"].required = True
