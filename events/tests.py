from datetime import timedelta

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


class EventListViewTests(TestCase):
    def test_event_list_returns_200(self):
        response = self.client.get(reverse("events:event_list"))
        self.assertEqual(response.status_code, 200)


class FavoriteToggleTests(TestCase):
    def test_toggle_adds_and_removes_from_session(self):
        event = Event.objects.create(
            title="Toggle Event",
            description="desc",
            date_time=timezone.now(),
            location="Somewhere",
        )
        url = reverse("events:favorite_toggle", args=[event.pk])

        self.client.post(url)
        self.assertIn(event.pk, self.client.session.get("favorite_ids", []))

        self.client.post(url)
        self.assertNotIn(event.pk, self.client.session.get("favorite_ids", []))


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
