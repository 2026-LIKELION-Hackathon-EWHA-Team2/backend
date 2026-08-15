from django.urls import path

from .views import (
    HospitalListView,
    HospitalProfileView,
    HospitalSignUpView,
    LoginView,
    LogoutView,
    PatientProfileView,
    PatientSignUpView,
)


app_name = "accounts"


urlpatterns = [
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