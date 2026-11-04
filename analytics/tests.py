from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from events.models import Category, Event

from .models import EventInteraction
from .services import build_dashboard

User = get_user_model()


class InteractionTrackingTests(TestCase):
    """REQ-30: the Events component records what visitors do."""

    def setUp(self):
        self.event = Event.objects.create(
            title="Concierto", description="d", date_time=timezone.now() + timedelta(days=5),
            location="x", ticket_url="https://tickets.example.com/1",
        )
        self.user = User.objects.create_user("ana@doday.co", "ana@doday.co", "pass12345!")
        self.staff = User.objects.create_user("admin@doday.co", "admin@doday.co", "pass12345!", is_staff=True)

    def _count(self, kind):
        return EventInteraction.objects.filter(event=self.event, kind=kind).count()

    def test_a_view_is_counted_once_per_session(self):
        url = reverse("events:event_detail", args=[self.event.pk])
        self.client.get(url)
        self.client.get(url)
        self.assertEqual(self._count(EventInteraction.Kind.VIEW), 1)

    def test_staff_browsing_is_not_counted(self):
        self.client.force_login(self.staff)
        self.client.get(reverse("events:event_detail", args=[self.event.pk]))
        self.assertEqual(self._count(EventInteraction.Kind.VIEW), 0)

    def test_saving_a_favorite_is_counted_but_removing_is_not(self):
        self.client.force_login(self.user)
        url = reverse("events:favorite_toggle", args=[self.event.pk])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(self._count(EventInteraction.Kind.FAVORITE), 1)

    def test_ticket_link_counts_and_redirects(self):
        response = self.client.get(reverse("events:event_tickets", args=[self.event.pk]))
        self.assertRedirects(response, self.event.ticket_url, fetch_redirect_response=False)
        self.assertEqual(self._count(EventInteraction.Kind.TICKET_CLICK), 1)

    def test_detail_page_uses_the_tracked_ticket_link(self):
        response = self.client.get(reverse("events:event_detail", args=[self.event.pk]))
        self.assertContains(response, reverse("events:event_tickets", args=[self.event.pk]))

    def test_pending_events_are_not_tracked(self):
        self.event.status = Event.Status.PENDING
        self.event.save()
        self.assertEqual(self.client.get(reverse("events:event_tickets", args=[self.event.pk])).status_code, 404)
        self.assertEqual(EventInteraction.objects.count(), 0)


class DashboardTests(TestCase):
    """REQ-30: indicators and access to the dashboard."""

    def setUp(self):
        music = Category.objects.create(name="Música")
        food = Category.objects.create(name="Gastronomía")
        soon = timezone.now() + timedelta(days=3)
        self.concert = Event.objects.create(title="Concierto", description="d", date_time=soon, location="x", category=music, is_free=False, ticket_url="https://t.example.com")
        self.fair = Event.objects.create(title="Feria", description="d", date_time=soon, location="x", category=food)
        Event.objects.create(title="Mercado", description="d", date_time=soon, location="x", category=food)
        K = EventInteraction.Kind
        for kind, event, times in [
            (K.VIEW, self.concert, 10), (K.FAVORITE, self.concert, 2), (K.TICKET_CLICK, self.concert, 3),
            (K.VIEW, self.fair, 4),
        ]:
            EventInteraction.objects.bulk_create(EventInteraction(event=event, kind=kind) for _ in range(times))
        self.staff = User.objects.create_user("admin@doday.co", "admin@doday.co", "pass12345!", is_staff=True)

    def test_kpis_and_rankings(self):
        data = build_dashboard(30)
        self.assertEqual(data["kpis"]["views"], 14)
        self.assertEqual(data["kpis"]["favorites"], 2)
        self.assertEqual(data["kpis"]["ticket_clicks"], 3)
        self.assertEqual(data["kpis"]["click_through_rate"], 21)  # 3 / 14
        # Concierto: 10 + 3*2 + 5*3 = 31; Feria: 4.
        self.assertEqual([row["event__title"] for row in data["top_events"]], ["Concierto", "Feria"])
        self.assertEqual(data["top_events"][0]["interest"], 31)
        self.assertEqual(data["top_events"][0]["bar"], 100)

    def test_interest_per_event_compares_demand_with_supply(self):
        with translation.override("en"):
            rows = {row["name"]: row for row in build_dashboard(30)["by_category"]}
        self.assertEqual(rows["Music"]["interest_per_event"], 31)  # one music event
        self.assertEqual(rows["Food"]["interest_per_event"], 2)  # 4 interest / 2 food events

    def test_old_interactions_fall_outside_the_period(self):
        EventInteraction.objects.update(created_at=timezone.now() - timedelta(days=40))
        self.assertFalse(build_dashboard(30)["has_data"])
        self.assertTrue(build_dashboard(90)["has_data"])

    def test_staff_can_open_the_dashboard(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("analytics:dashboard"), {"days": 7})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Events with the most interest")
        self.assertContains(response, "Concierto")

    def test_dashboard_in_spanish_keeps_bar_widths_valid(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("analytics:dashboard"), HTTP_ACCEPT_LANGUAGE="es")
        self.assertContains(response, "Analítica")
        self.assertNotContains(response, "width: 12,")

    def test_regular_users_cannot_open_the_dashboard(self):
        user = User.objects.create_user("ana@doday.co", "ana@doday.co", "pass12345!")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("analytics:dashboard")).status_code, 403)

    def test_anonymous_users_are_sent_to_login(self):
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
