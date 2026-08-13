from django.urls import path
from .views import *

app_name = 'accounts'

urlpatterns = [
    path('signup/', SignUpView.as_view()),
    path("login/", LoginView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("patient-profile/", PatientProfileView.as_view()),
    path("hospital-profile/", HospitalProfileView.as_view()),
]