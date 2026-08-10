from django.urls import path

from .views import (
    AdverseEffectUpdateView,
    CaseChatMessageListCreateView,
    CaseTransferView,
    MedicalCaseDetailView,
    MedicalCaseListCreateView,
    CaseSyncRequestListCreateView,
    CaseSyncRequestReviewView,
)


urlpatterns = [
    path(
        "",
        MedicalCaseListCreateView.as_view(),
        name="case-list-create",
    ),
    path(
        "<int:case_id>/",
        MedicalCaseDetailView.as_view(),
        name="case-detail",
    ),
    path(
        "<int:case_id>/adverse-effects/",
        AdverseEffectUpdateView.as_view(),
        name="case-adverse-effects",
    ),
    path(
        "<int:case_id>/transfer/",
        CaseTransferView.as_view(),
        name="case-transfer",
    ),
    path(
    "<int:case_id>/chat/rooms/<int:room_id>/messages/",
    CaseChatMessageListCreateView.as_view(),
    name="case-chat-message-list-create",
    ),
    path(
    "sync-requests/",
    CaseSyncRequestListCreateView.as_view(),
    name="case-sync-request-list-create",
    ),
    path(
        "sync-requests/<int:sync_request_id>/review/",
        CaseSyncRequestReviewView.as_view(),
        name="case-sync-request-review",
    ),
]