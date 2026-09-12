from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    HospitalListView,
    HospitalProfileView,
    HospitalSignUpView,
    LoginView,
    LogoutView,
    MedicalSpecialtyOptionsView,
    PatientProfileView,
    PatientSignUpView,
)


app_name = "accounts"


urlpatterns = [
    path(
        "specialties/options/",
        MedicalSpecialtyOptionsView.as_view(),
        name="medical-specialty-options",
    ),
    path(
        "signup/patient/",
        PatientSignUpView.as_view(),
        name="patient-signup",
    ),
    path(
        "signup/hospital/",
        HospitalSignUpView.as_view(),
        name="hospital-signup",
    ),
    path(
        "login/",
        LoginView.as_view(),
        name="login",
    ),
    path(
        "token/refresh/",
        TokenRefreshView.as_view(),
        name="token-refresh",
    ),
    path(
        "logout/",
        LogoutView.as_view(),
        name="logout",
    ),
    path(
        "patient-profile/",
        PatientProfileView.as_view(),
        name="patient-profile",
    ),
    path(
        "hospital-profile/",
        HospitalProfileView.as_view(),
        name="hospital-profile",
    ),
    path(
        "hospitals/",
        HospitalListView.as_view(),
        name="hospital-list",
    ),
]
