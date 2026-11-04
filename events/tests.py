from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Category, Event

User = get_user_model()


class EventModelTests(TestCase):
    def test_str_representation(self):
        event = Event.objects.create(
            title="Feria Local",
            description="desc",
            date_time=timezone.now(),
            location="Plaza Mayor",
        )
        self.assertEqual(str(event), "Feria Local")

    def test_clean_rejects_end_date_before_start(self):
        event = Event(
            title="Bad Event",
            description="desc",
            date_time=timezone.now(),
            end_date=timezone.now() - timedelta(days=1),
            location="Somewhere",
        )
        with self.assertRaises(Exception):
            event.full_clean()

    def test_google_maps_url_formatted_with_dot_decimal(self):
        event = Event(
            title="Test Event",
            description="desc",
            date_time=timezone.now(),
            location="Plaza",
            latitude=6.244,
            longitude=-75.581,
        )
        self.assertEqual(
            event.google_maps_url,
            "https://www.google.com/maps/search/?api=1&query=6.244,-75.581",
        )

    def test_google_maps_url_returns_none_when_coords_missing(self):
        event = Event(
            title="Test Event",
            description="desc",
            date_time=timezone.now(),
            location="Plaza",
            latitude=6.244,
            longitude=None,
        )
        self.assertIsNone(event.google_maps_url)


class EventBadgeTests(TestCase):
    """REQ-23: real-time status badges."""

    def _event(self, **kwargs):
        defaults = {
            "title": "Badge Event",
            "description": "desc",
            "date_time": timezone.now(),
            "location": "Plaza",
            "is_free": False,
        }
        return Event(**{**defaults, **kwargs})

    def _labels(self, event):
        return [badge["label"] for badge in event.badges]

    def test_event_starting_today_is_badged_hoy(self):
        event = self._event(date_time=timezone.now())
        self.assertIn("Today", self._labels(event))

    def test_event_within_next_week_is_badged_esta_semana(self):
        event = self._event(date_time=timezone.now() + timedelta(days=3))
        self.assertEqual(self._labels(event), ["This week"])

    def test_event_further_away_gets_no_date_badge(self):
        event = self._event(date_time=timezone.now() + timedelta(days=30))
        self.assertEqual(self._labels(event), [])

    def test_finished_event_gets_no_date_badge(self):
        event = self._event(
            date_time=timezone.now() - timedelta(days=10),
            end_date=timezone.now() - timedelta(days=9),
        )
        self.assertEqual(self._labels(event), [])

    def test_ongoing_multi_day_event_is_badged_hoy(self):
        """A festival that started before today but runs past it is happening now."""
        event = self._event(
            date_time=timezone.now() - timedelta(days=2),
            end_date=timezone.now() + timedelta(days=2),
        )
        self.assertEqual(self._labels(event), ["Today"])

    def test_hoy_takes_precedence_over_esta_semana(self):
        event = self._event(date_time=timezone.now())
        self.assertNotIn("This week", self._labels(event))

    def test_free_event_is_badged_gratis(self):
        event = self._event(date_time=timezone.now() + timedelta(days=30), is_free=True)
        self.assertEqual(self._labels(event), ["Free"])

    def test_paid_event_is_not_badged_gratis(self):
        event = self._event(date_time=timezone.now() + timedelta(days=30), is_free=False)
        self.assertNotIn("Free", self._labels(event))

    def test_free_badge_combines_with_date_badge(self):
        event = self._event(date_time=timezone.now(), is_free=True)
        self.assertEqual(self._labels(event), ["Today", "Free"])

    def test_badges_carry_a_css_slug(self):
        event = self._event(date_time=timezone.now(), is_free=True)
        self.assertEqual([badge["slug"] for badge in event.badges], ["today", "free"])

    def test_event_list_renders_badges(self):
        Event.objects.create(
            title="Evento de Hoy",
            description="desc",
            date_time=timezone.now(),
            location="Plaza",
            is_free=True,
        )
        response = self.client.get(reverse("events:event_list"))
        self.assertContains(response, "event-badge-today")
        self.assertContains(response, "event-badge-free")

    def test_event_detail_renders_badges(self):
        event = Event.objects.create(
            title="Evento de Hoy",
            description="desc",
            date_time=timezone.now(),
            location="Plaza",
            is_free=True,
        )
        response = self.client.get(reverse("events:event_detail", args=[event.pk]))
        self.assertContains(response, "event-badge-today")
        self.assertContains(response, "event-badge-free")


class EventDetailViewTests(TestCase):
    def test_renders_google_maps_link_when_coords_exist(self):
        event = Event.objects.create(
            title="Maps Event",
            description="desc",
            date_time=timezone.now(),
            location="Somewhere",
            latitude=6.244,
            longitude=-75.581,
        )
        response = self.client.get(reverse("events:event_detail", args=[event.pk]))
        self.assertContains(response, "Open in Google Maps")
        self.assertContains(response, "https://www.google.com/maps/search/?api=1&amp;query=6.244000,-75.581000")
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')

    def test_omits_google_maps_link_when_coords_missing(self):
        event = Event.objects.create(
            title="No Coords Event",
            description="desc",
            date_time=timezone.now(),
            location="Somewhere",
        )
        response = self.client.get(reverse("events:event_detail", args=[event.pk]))
        self.assertNotContains(response, "Open in Google Maps")

    def test_renders_share_button(self):
        event = Event.objects.create(
            title="Shareable Event",
            description="desc",
            date_time=timezone.now(),
            location="Somewhere",
        )
        response = self.client.get(reverse("events:event_detail", args=[event.pk]))
        self.assertContains(response, 'id="share-button"')

    def test_anonymous_user_sees_login_prompt_instead_of_favorite_button(self):
        event = Event.objects.create(
            title="Favorite Prompt Event",
            description="desc",
            date_time=timezone.now(),
            location="Somewhere",
        )
        response = self.client.get(reverse("events:event_detail", args=[event.pk]))
        self.assertContains(response, "Log in to save favorites")
        self.assertNotContains(response, "Save to favorites")


class EventListViewTests(TestCase):
    def test_event_list_returns_200(self):
        response = self.client.get(reverse("events:event_list"))
        self.assertEqual(response.status_code, 200)


class FavoriteToggleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="guest", password="pw12345")

    def test_toggle_adds_and_removes_from_session_when_logged_in(self):
        event = Event.objects.create(
            title="Toggle Event",
            description="desc",
            date_time=timezone.now(),
            location="Somewhere",
        )
        url = reverse("events:favorite_toggle", args=[event.pk])
        self.client.login(username="guest", password="pw12345")

        self.client.post(url)
        self.assertIn(event.pk, self.client.session.get("favorite_ids", []))

        self.client.post(url)
        self.assertNotIn(event.pk, self.client.session.get("favorite_ids", []))

    def test_anonymous_user_is_redirected_to_login(self):
        event = Event.objects.create(
            title="Toggle Event",
            description="desc",
            date_time=timezone.now(),
            location="Somewhere",
        )
        url = reverse("events:favorite_toggle", args=[event.pk])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertNotIn(event.pk, self.client.session.get("favorite_ids", []))

    def test_anonymous_user_cannot_view_favorites_list(self):
        response = self.client.get(reverse("events:favorites_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)


class EventPermissionsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="staff", password="pw12345", is_staff=True)
        self.regular_user = User.objects.create_user(username="regular", password="pw12345")

    def test_non_staff_cannot_create_event(self):
        self.client.login(username="regular", password="pw12345")
        response = self.client.get(reverse("events:event_create"))
        self.assertEqual(response.status_code, 403)

    def test_staff_can_create_event(self):
        self.client.login(username="staff", password="pw12345")
        response = self.client.get(reverse("events:event_create"))
        self.assertEqual(response.status_code, 200)


class InterfaceLanguageTests(TestCase):
    """REQ-29: English by default, Spanish for residents, switchable in the header."""

    def setUp(self):
        self.event = Event.objects.create(
            title="Concierto",
            description="desc",
            date_time=timezone.now() + timedelta(days=30),
            location="Medellín",
            latitude=6.244,
            longitude=-75.581,
            is_free=False,
            price=Decimal("85000"),
        )

    def test_english_is_the_default(self):
        response = self.client.get(reverse("events:event_list"))
        self.assertContains(response, '<html lang="en">')
        self.assertContains(response, "Upcoming events")
        self.assertContains(response, "Free events only")

    def test_spanish_browser_gets_spanish(self):
        response = self.client.get(reverse("events:event_list"), HTTP_ACCEPT_LANGUAGE="es-CO,es;q=0.9")
        self.assertContains(response, '<html lang="es">')
        self.assertContains(response, "Próximos eventos")
        self.assertContains(response, "Solo eventos gratis")
        self.assertNotContains(response, "Upcoming events")

    def test_language_switcher_changes_the_language(self):
        response = self.client.post(
            reverse("set_language"), {"language": "es", "next": reverse("events:event_list")}
        )
        self.assertRedirects(response, reverse("events:event_list"))
        response = self.client.get(reverse("events:event_list"))
        self.assertContains(response, "Próximos eventos")

        self.client.post(reverse("set_language"), {"language": "en", "next": "/"})
        response = self.client.get(reverse("events:event_list"))
        self.assertContains(response, "Upcoming events")

    def test_header_shows_both_languages(self):
        response = self.client.get(reverse("events:event_list"))
        self.assertContains(response, 'name="language" value="en"')
        self.assertContains(response, 'name="language" value="es"')

    def test_price_uses_thousands_separator_per_language(self):
        response = self.client.get(reverse("events:event_detail", args=[self.event.pk]))
        self.assertContains(response, "$85,000")
        self.assertNotContains(response, "85000.00")
        response = self.client.get(
            reverse("events:event_detail", args=[self.event.pk]), HTTP_ACCEPT_LANGUAGE="es"
        )
        self.assertContains(response, "$85.000")

    def test_badges_follow_the_language(self):
        self.event.is_free = True
        self.event.save()
        response = self.client.get(reverse("events:event_list"), HTTP_ACCEPT_LANGUAGE="es")
        self.assertContains(response, "Gratis")

    def test_map_coordinates_keep_a_dot_in_spanish(self):
        # Spanish formats decimals with a comma ("6,244"), which would break the
        # Leaflet JavaScript; coordinates must always be rendered with a dot.
        response = self.client.get(
            reverse("events:event_detail", args=[self.event.pk]), HTTP_ACCEPT_LANGUAGE="es"
        )
        self.assertContains(response, "6.244000")
        self.assertNotContains(response, "6,244000")


class CategoryTranslationTests(TestCase):
    """REQ-29: categories arrive in either language and show in the active one."""

    def test_known_names_get_both_languages(self):
        spanish = Category.objects.create(name="Música")
        english = Category.objects.create(name="Sports")
        self.assertEqual((spanish.name_en, spanish.name_es), ("Music", "Música"))
        self.assertEqual((english.name_en, english.name_es), ("Sports", "Deportes"))

    def test_unknown_name_falls_back_to_the_original(self):
        category = Category.objects.create(name="Salsa caleña")
        self.assertEqual(category.display_name, "Salsa caleña")

    def test_card_and_filter_follow_the_language(self):
        category = Category.objects.create(name="Música")
        Event.objects.create(
            title="Concierto",
            description="desc",
            date_time=timezone.now() + timedelta(days=30),
            location="Medellín",
            category=category,
        )
        response = self.client.get(reverse("events:event_list"))
        self.assertContains(response, '<span class="event-category">Music</span>')
        response = self.client.get(reverse("events:event_list"), HTTP_ACCEPT_LANGUAGE="es")
        self.assertContains(response, '<span class="event-category">Música</span>')
        self.assertNotContains(response, '<span class="event-category">Music</span>')
