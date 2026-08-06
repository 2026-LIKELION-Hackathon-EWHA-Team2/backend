from django.urls import path

from .views import (
    AdverseEffectUpdateView,
    CaseChatMessageListCreateView,
    CaseTransferView,
    MedicalCaseDetailView,
    MedicalCaseListCreateView,
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
]