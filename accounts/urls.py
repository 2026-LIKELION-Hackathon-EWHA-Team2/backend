from django.urls import path

from .views import (
    HospitalListView,
    LoginView,
    LogoutView,
    SignUpView,
)


app_name = "accounts"


urlpatterns = [
    path("signup/", SignUpView.as_view()),
    path("login/", LoginView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("hospitals/", HospitalListView.as_view()),
]