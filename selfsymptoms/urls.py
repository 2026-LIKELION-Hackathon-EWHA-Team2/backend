from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PatientSymptomCaseViewSet


router = DefaultRouter()

router.register(
    r"symptom-cases",
    PatientSymptomCaseViewSet,
    basename="symptom-case",
)

urlpatterns = [
    path("", include(router.urls)),
]
