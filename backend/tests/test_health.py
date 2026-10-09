from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class HealthEndpointTests(APITestCase):
    def test_health_endpoint_is_public_and_versioned(self):
        response = self.client.get(reverse("api-v1-health"))

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "status": "ok",
            "service": "lotneeti-api",
            "apiVersion": "v1",
        }
