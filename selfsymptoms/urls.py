from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PatientSymptomCaseViewSet,
    PatientSymptomImageViewSet,
)


router = DefaultRouter()

router.register(
    r"symptom-cases",
    PatientSymptomCaseViewSet,
    basename="symptom-case",
)

router.register(
    r"symptom-images",
    PatientSymptomImageViewSet,
    basename="symptom-image",
)


urlpatterns = [
    path("", include(router.urls)),
]