from django.urls import path

from .views import (
    HospitalListView,
    HospitalProfileView,
    LoginView,
    LogoutView,
    PatientProfileView,
    SignUpView,
)


app_name = "accounts"


urlpatterns = [
    path(
        "signup/",
        SignUpView.as_view(),
    ),
    path(
        "login/",
        LoginView.as_view(),
    ),
    path(
        "logout/",
        LogoutView.as_view(),
    ),
    path(
        "patient-profile/",
        PatientProfileView.as_view(),
    ),
    path(
        "hospital-profile/",
        HospitalProfileView.as_view(),
    ),
    path(
        "hospitals/",
        HospitalListView.as_view(),
    ),
]