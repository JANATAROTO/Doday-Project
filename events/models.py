from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.formats import number_format
from django.utils.translation import get_language, gettext, gettext_lazy as _

from .category_names import bilingual_names


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)
    # REQ-29: name shown in each interface language. Filled in automatically
    # for known categories (events/category_names.py); empty means "use name".
    name_en = models.CharField("name (English)", max_length=50, blank=True)
    name_es = models.CharField("name (Spanish)", max_length=50, blank=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        known = bilingual_names(self.name)
        if known:
            self.name_en = self.name_en or known[0]
            self.name_es = self.name_es or known[1]
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        """The category name in the active interface language."""
        if (get_language() or "").startswith("es"):
            return self.name_es or self.name
        return self.name_en or self.name


class EventQuerySet(models.QuerySet):
    def published(self):
        """REQ-24/25: only approved events reach the catalog, search, map and
        favorites. Community proposals stay hidden until a moderator approves
        them; every public listing goes through this one method."""
        return self.filter(status=Event.Status.APPROVED)

    def pending(self):
        return self.filter(status=Event.Status.PENDING)


class Event(models.Model):
    class Status(models.TextChoices):
        # Events created by staff, synced from Ticketmaster or seeded are
        # published right away; only community proposals start as pending.
        PENDING = "pending", _("Pending review")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="events",
        null=True,
        blank=True,
        help_text="Only the organizer who created the event can edit it (RF5).",
    )
    title = models.CharField(max_length=150)
    description = models.TextField()
    date_time = models.DateTimeField(help_text="Start date and time (required).")
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="End date and time, for multi-day events (fairs, festivals). Leave empty for single-day events.",
    )
    location = models.CharField(
        max_length=255,
        help_text="Address or place name (exact map coordinates come with RF1).",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, related_name="events"
    )
    is_free = models.BooleanField(default=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Leave empty if the event is free.",
    )
    ticket_url = models.URLField(
        blank=True,
        help_text="Where attendees can buy tickets for this event (RF21). Leave empty if there's no ticketing link.",
    )

    # REQ-13: external API traceability — lets update_or_create be idempotent
    external_source = models.CharField(
        max_length=50,
        blank=True,
        help_text="Source API slug (e.g. 'ticketmaster'). Empty for manually-created events.",
    )
    external_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Original ID in the external source. Used together with external_source for deduplication.",
    )

    # REQ-24: community submissions. REQ-25: moderation status.
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.APPROVED,
        db_index=True,
        help_text="Only approved events are shown to the public (REQ-25).",
    )
    submitter_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Who proposed the event through the public form (REQ-24). Empty for staff events.",
    )
    submitter_email = models.EmailField(
        blank=True,
        help_text="Contact email of the person who proposed the event (REQ-24).",
    )

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["date_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["external_source", "external_id"],
                name="unique_external_event",
                condition=~models.Q(external_source=""),
            )
        ]

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        return self.status == self.Status.APPROVED

    def clean(self):
        if self.end_date and self.end_date < self.date_time:
            raise ValidationError({"end_date": _("End date must be on or after the start date.")})

    @property
    def badges(self):
        """REQ-23: real-time status badges rendered on every event card.

        "Today" takes precedence over "This week" so a card never shows two
        overlapping date badges, and an event that already finished gets no
        date badge at all. "Free" is independent and can accompany either.
        Labels follow the active language (REQ-29); the slug drives the CSS.

        Pure Python over fields that are already loaded — no extra queries,
        so it is safe to call once per card in a list.
        """
        badges = []
        today = timezone.localdate()
        first_day = timezone.localtime(self.date_time).date()
        # Multi-day events (fairs, festivals) run until end_date; single-day
        # ones start and finish on the same date.
        last_day = timezone.localtime(self.end_date).date() if self.end_date else first_day

        if first_day <= today <= last_day:
            badges.append({"label": gettext("Today"), "slug": "today"})
        elif today < first_day <= today + timedelta(days=7):
            badges.append({"label": gettext("This week"), "slug": "this-week"})

        if self.is_free:
            badges.append({"label": gettext("Free"), "slug": "free"})

        return badges

    @property
    def price_label(self):
        """REQ-29: one price format for cards, detail page and map pop-ups.

        Prices are Colombian pesos without cents, grouped with the active
        language's thousands separator ("$85,000" in English, "$85.000" in
        Spanish) instead of the raw "$85000.00".
        """
        if self.is_free:
            return gettext("Free")
        if self.price is None:
            return gettext("Price not available")
        amount = number_format(self.price, decimal_pos=0, force_grouping=True)
        return f"${amount}"

    @property
    def google_maps_url(self):
        if self.latitude is not None and self.longitude is not None:
            lat_str = str(self.latitude).replace(",", ".")
            lng_str = str(self.longitude).replace(",", ".")
            return f"https://www.google.com/maps/search/?api=1&query={lat_str},{lng_str}"
        return None

