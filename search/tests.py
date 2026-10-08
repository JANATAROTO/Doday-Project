from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from events.models import Category, Event
from search.forms import SORT_DATE, SORT_DISTANCE, EventFilterForm
from search.services import filter_events

User = get_user_model()


class FilterEventsTests(TestCase):
    def setUp(self):
        organizer = User.objects.create_user(username="organizer", password="pw12345")
        self.music = Category.objects.create(name="Music")
        self.food = Category.objects.create(name="Food")
        now = timezone.now()

        self.free_music_event = Event.objects.create(
            title="Free Jazz Night",
            description="Live jazz in the park",
            date_time=now + timedelta(days=1),
            location="Park",
            category=self.music,
            is_free=True,
            organizer=organizer,
        )
        self.paid_food_event = Event.objects.create(
            title="Food Festival",
            description="Taste local dishes",
            date_time=now + timedelta(days=5),
            location="Downtown",
            category=self.food,
            is_free=False,
            price=20000,
            organizer=organizer,
        )

    def test_keyword_filter_matches_title_or_description(self):
        form = EventFilterForm({"q": "jazz"})
        result = filter_events(Event.objects.all(), form)
        self.assertEqual(list(result), [self.free_music_event])

    def test_category_filter(self):
        form = EventFilterForm({"category": [self.food.pk]})
        result = filter_events(Event.objects.all(), form)
        self.assertEqual(list(result), [self.paid_food_event])

    def test_free_only_filter(self):
        form = EventFilterForm({"free_only": True})
        result = filter_events(Event.objects.all(), form)
        self.assertEqual(list(result), [self.free_music_event])

    def test_invalid_form_returns_unfiltered_queryset(self):
        # date_from after date_to makes the form invalid.
        form = EventFilterForm({"date_from": "2030-01-02", "date_to": "2030-01-01"})
        result = filter_events(Event.objects.all(), form)
        self.assertEqual(result.count(), 2)


class RadiusFilterTests(TestCase):
    """REQ-08: filter events within N km of the accommodation."""

    # Parque Lleras — the origin used by every test here.
    ORIGIN = (Decimal("6.208900"), Decimal("-75.568000"))

    def setUp(self):
        organizer = User.objects.create_user(username="organizer", password="pw12345")
        now = timezone.now()

        def make_event(title, latitude=None, longitude=None):
            return Event.objects.create(
                title=title,
                description="desc",
                date_time=now + timedelta(days=1),
                location=title,
                latitude=latitude,
                longitude=longitude,
                organizer=organizer,
            )

        # ~3.9 km from the origin.
        self.nearby = make_event("Teatro Metropolitano", Decimal("6.243177"), Decimal("-75.577508"))
        # ~7.9 km from the origin.
        self.far = make_event("Comuna 13", Decimal("6.256274"), Decimal("-75.621543"))
        # No physical venue at all — a legitimate catalogue entry.
        self.online = make_event("Reto en línea")

    def _filter(self, data, origin=None):
        form = EventFilterForm(data)
        return filter_events(Event.objects.all(), form, origin=origin or self.ORIGIN)

    def test_radius_keeps_only_events_inside_it(self):
        result = self._filter({"radius_km": "5"})
        self.assertEqual([event.title for event in result], [self.nearby.title])

    def test_wider_radius_keeps_both_located_events(self):
        result = self._filter({"radius_km": "10"})
        self.assertCountEqual(
            [event.title for event in result], [self.nearby.title, self.far.title]
        )

    def test_events_without_coordinates_are_excluded_by_a_radius(self):
        result = self._filter({"radius_km": "500"})
        self.assertNotIn(self.online.title, [event.title for event in result])

    def test_events_without_coordinates_are_kept_when_no_radius_is_given(self):
        result = self._filter({})
        self.assertIn(self.online.title, [event.title for event in result])

    def test_distance_is_attached_to_every_located_event(self):
        result = {event.title: event.distance_km for event in self._filter({})}
        self.assertAlmostEqual(result[self.nearby.title], 3.9, delta=0.2)
        self.assertAlmostEqual(result[self.far.title], 7.9, delta=0.2)
        self.assertIsNone(result[self.online.title])

    def test_radius_is_ignored_without_an_accommodation(self):
        form = EventFilterForm({"radius_km": "1"})
        result = filter_events(Event.objects.all(), form, origin=None)
        # No origin to measure from: everything stays, as a plain queryset.
        self.assertEqual(result.count(), 3)

    def test_radius_combines_with_the_other_filters(self):
        # Both located events are inside a 10 km radius, so only the price
        # filter can tell them apart.
        self.far.is_free = False
        self.far.price = 20000
        self.far.save()

        result = self._filter({"radius_km": "10", "free_only": True})

        self.assertEqual([event.title for event in result], [self.nearby.title])

    def test_negative_radius_is_rejected(self):
        form = EventFilterForm({"radius_km": "-5"})
        self.assertFalse(form.is_valid())
        self.assertIn("radius_km", form.errors)

    def test_distances_are_attached_with_an_unbound_form(self):
        """A plain page load builds the form unbound — distances must still show."""
        result = filter_events(Event.objects.all(), EventFilterForm(), origin=self.ORIGIN)

        distances = {event.title: event.distance_km for event in result}
        self.assertAlmostEqual(distances[self.nearby.title], 3.9, delta=0.2)
        self.assertIn(self.online.title, distances)


class ProximitySortTests(TestCase):
    """REQ-14: list events sorted by proximity to the accommodation or by date."""

    # Parque Lleras — the origin used by every test here.
    ORIGIN = (Decimal("6.208900"), Decimal("-75.568000"))

    def setUp(self):
        organizer = User.objects.create_user(username="organizer", password="pw12345")
        now = timezone.now()

        def make_event(title, days_ahead, latitude=None, longitude=None):
            return Event.objects.create(
                title=title,
                description="desc",
                date_time=now + timedelta(days=days_ahead),
                location=title,
                latitude=latitude,
                longitude=longitude,
                organizer=organizer,
            )

        # Deliberately created so date order and distance order disagree: the
        # soonest event is the farthest away. A test that passed under both
        # orders would prove nothing.
        self.far_and_soon = make_event(
            "Comuna 13", 1, Decimal("6.256274"), Decimal("-75.621543")  # ~7.9 km
        )
        self.near_and_later = make_event(
            "Teatro Metropolitano", 5, Decimal("6.243177"), Decimal("-75.577508")  # ~3.9 km
        )
        self.middle = make_event(
            "Jardín Botánico", 9, Decimal("6.270548"), Decimal("-75.563529")  # ~6.9 km
        )
        # No physical venue at all — a legitimate catalogue entry.
        self.online = make_event("Reto en línea", 3)

    def _sorted_titles(self, data, origin=True):
        form = EventFilterForm(data)
        result = filter_events(
            Event.objects.all(), form, origin=self.ORIGIN if origin else None
        )
        return [event.title for event in result]

    def test_distance_sort_puts_the_nearest_first(self):
        titles = self._sorted_titles({"sort": SORT_DISTANCE})

        self.assertEqual(
            titles[:3],
            [self.near_and_later.title, self.middle.title, self.far_and_soon.title],
        )

    def test_events_without_coordinates_go_last(self):
        """Never compare a None distance — they belong at the end as a group."""
        titles = self._sorted_titles({"sort": SORT_DISTANCE})

        self.assertEqual(titles[-1], self.online.title)

    def test_date_sort_is_the_default(self):
        """An empty sort means by start date, as Event.Meta.ordering says."""
        titles = self._sorted_titles({})

        self.assertEqual(
            titles,
            [
                self.far_and_soon.title,
                self.online.title,
                self.near_and_later.title,
                self.middle.title,
            ],
        )

    def test_date_sort_can_be_asked_for_explicitly(self):
        self.assertEqual(
            self._sorted_titles({"sort": SORT_DATE}), self._sorted_titles({})
        )

    def test_proximity_sort_is_ignored_without_an_accommodation(self):
        """No origin to measure from: keep the date order instead of failing."""
        form = EventFilterForm({"sort": SORT_DISTANCE})
        result = filter_events(Event.objects.all(), form, origin=None)

        self.assertEqual(
            [event.title for event in result],
            [
                self.far_and_soon.title,
                self.online.title,
                self.near_and_later.title,
                self.middle.title,
            ],
        )

    def test_proximity_sort_combines_with_the_radius(self):
        """REQ-08 drops the unlocated events; REQ-14 orders what is left."""
        titles = self._sorted_titles({"sort": SORT_DISTANCE, "radius_km": "7"})

        self.assertEqual(titles, [self.near_and_later.title, self.middle.title])

    def test_proximity_sort_combines_with_the_other_filters(self):
        titles = self._sorted_titles({"sort": SORT_DISTANCE, "q": "Teatro"})

        self.assertEqual(titles, [self.near_and_later.title])

    def test_equal_distances_keep_their_date_order(self):
        """The sort is stable, so distance ties fall back to the start date."""
        twin = Event.objects.create(
            title="Teatro Metropolitano (segunda fecha)",
            description="desc",
            date_time=self.near_and_later.date_time + timedelta(days=1),
            location="Teatro Metropolitano",
            latitude=self.near_and_later.latitude,
            longitude=self.near_and_later.longitude,
            organizer=self.near_and_later.organizer,
        )

        titles = self._sorted_titles({"sort": SORT_DISTANCE})

        self.assertEqual(titles[:2], [self.near_and_later.title, twin.title])

    def test_an_invalid_sort_falls_back_to_date_order(self):
        """A bad ?sort= must not reorder the list under the user's feet."""
        form = EventFilterForm({"sort": "nearest-by-vibes"})
        self.assertFalse(form.is_valid())

        result = filter_events(Event.objects.all(), form, origin=self.ORIGIN)

        self.assertEqual([event.title for event in result][0], self.far_and_soon.title)

    def test_distance_is_still_attached_when_sorting_by_date(self):
        form = EventFilterForm({"sort": SORT_DATE})
        result = filter_events(Event.objects.all(), form, origin=self.ORIGIN)

        distances = {event.title: event.distance_km for event in result}
        self.assertAlmostEqual(distances[self.near_and_later.title], 3.9, delta=0.2)
