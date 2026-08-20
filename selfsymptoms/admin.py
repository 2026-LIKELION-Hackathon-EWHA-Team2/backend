from django.contrib import admin

from .models import (
    DiagnosisAnalysis,
    PatientSymptomArea,
    PatientSymptomCase,
    PatientSymptomImage,
    PatientSymptomType,
)


class PatientSymptomImageInline(admin.TabularInline):
    model = PatientSymptomImage
    extra = 0
    min_num = 1
    max_num = 6
    validate_min = True
    validate_max = True
    fields = (
        "image",
        "display_order",
    )


class PatientSymptomAreaInline(admin.TabularInline):
    model = PatientSymptomArea
    extra = 0
    min_num = 1
    validate_min = True
    fields = (
        "area_type",
    )


class PatientSymptomTypeInline(admin.TabularInline):
    model = PatientSymptomType
    extra = 0
    min_num = 1
    validate_min = True
    fields = (
        "symptom_type",
        "custom_symptom",
    )


@admin.register(PatientSymptomCase)
class PatientSymptomCaseAdmin(admin.ModelAdmin):
    list_display = (
        "symptom_case_id",
        "patient",
        "diagnosed_hospital",
        "status",
        "symptom_start_date",
        "pain_level",
        "created_at",
    )
    list_filter = (
        "status",
        "onset_timing",
        "pain_level",
        "created_at",
    )
    search_fields = (
        "patient__user__name",
        "patient__user__username",
        "diagnosed_hospital__user__name",
        "description",
    )
    autocomplete_fields = (
        "patient",
        "diagnosed_hospital",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    inlines = (
        PatientSymptomImageInline,
        PatientSymptomAreaInline,
        PatientSymptomTypeInline,
    )
    fieldsets = (
        (
            "기본 정보",
            {
                "fields": (
                    "patient",
                    "diagnosed_hospital",
                    "status",
                )
            },
        ),
        (
            "증상 정보",
            {
                "fields": (
                    "symptom_start_date",
                    "onset_timing",
                    "pain_level",
                    "description",
                )
            },
        ),
        (
            "진단서",
            {
                "fields": (
                    "diagnosis_document",
                )
            },
        ),
        (
            "관리 정보",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(DiagnosisAnalysis)
class DiagnosisAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        "diagnosis_analysis_id",
        "symptom_case",
        "analyzed_at",
        "created_at",
    )
    search_fields = (
        "symptom_case__patient__user__name",
    )
    readonly_fields = (
        "extracted_text",
        "analysis_result",
        "analyzed_at",
        "created_at",
        "updated_at",
    )