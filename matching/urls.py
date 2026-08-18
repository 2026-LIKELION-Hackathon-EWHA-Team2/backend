from django.urls import path

from .views import (
    HospitalMatchConsentView,
    HospitalMatchRequestCreateView,
    HospitalMatchRequestDetailView,
    NetworkHospitalDetailView,
    NetworkHospitalListView,
    NetworkHospitalSelectView,
    HospitalRecommendationListView,
    HospitalRecommendationSelectView,
)


urlpatterns = [

    path(
        "network-hospitals/",
        NetworkHospitalListView.as_view(),
        name="network-hospital-list",
    ),

    path(
        "network-hospitals/<int:hospital_id>/",
        NetworkHospitalDetailView.as_view(),
        name="network-hospital-detail",
    ),

    path(
        "network-hospitals/<int:hospital_id>/select/",
        NetworkHospitalSelectView.as_view(),
        name="network-hospital-select",
    ),

    # 병원 매칭 요청 + AI 추천 생성
    path(
        "requests/",
        HospitalMatchRequestCreateView.as_view(),
        name="match-request-create",
    ),

    # 매칭 요청 상세
    path(
        "requests/<int:match_request_id>/",
        HospitalMatchRequestDetailView.as_view(),
        name="match-request-detail",
    ),

    # 선택 병원 매칭 동의
    path(
        "requests/<int:match_request_id>/consent/",
        HospitalMatchConsentView.as_view(),
        name="match-request-consent",
    ),

    # 추천 병원 목록
    path(
        "requests/<int:match_request_id>/recommendations/",
        HospitalRecommendationListView.as_view(),
        name="recommendation-list",
    ),

    # 추천 병원 선택
    path(
        "recommendations/<int:recommendation_id>/select/",
        HospitalRecommendationSelectView.as_view(),
        name="recommendation-select",
    ),
]
