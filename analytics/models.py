from django.db import models
from django.utils.translation import gettext_lazy as _


class EventInteraction(models.Model):
    """REQ-30: one row per visitor interaction with an event.

    Analytics component: records what the public does (open an event, save it
    to favorites, follow the ticket link) so the dashboard can show demand,
    not only the catalog supply. No personal data is stored: no user, no IP,
    only the event, the kind of interaction and when it happened.
    """

    class Kind(models.TextChoices):
        VIEW = "view", _("View")
        FAVORITE = "favorite", _("Saved to favorites")
        TICKET_CLICK = "ticket_click", _("Ticket link click")

    event = models.ForeignKey(
        "events.Event", on_delete=models.CASCADE, related_name="interactions"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["kind", "created_at"])]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.event} · {self.created_at:%Y-%m-%d %H:%M}"
