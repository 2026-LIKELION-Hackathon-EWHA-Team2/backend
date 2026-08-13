from django.urls import path

from .views import (
    HospitalMatchRequestCreateView,
    HospitalMatchRequestDetailView,
    HospitalRecommendationListView,
    HospitalRecommendationSelectView,
)


urlpatterns = [

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