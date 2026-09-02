from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from events.models import Category, Event
from search.forms import EventFilterForm
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
