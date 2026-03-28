from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase


class LoginAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="saleem", password="secret123")

    def test_login_returns_token_for_valid_credentials(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "saleem", "password": "secret123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)

    def test_login_requires_username_and_password(self):
        response = self.client.post("/api/auth/login/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)
        self.assertIn("password", response.data)
