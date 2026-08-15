from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    User,
    PatientProfile,
    HospitalProfile,
    MedicalSpecialty,
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "추가 정보",
            {
                "fields": (
                    "name",
                    "user_type",
                    "preferred_language",
                    "terms_agreed",
                    "privacy_agreed",
                    "overseas_info_agreed",
                    "marketing_agreed",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "추가 정보",
            {
                "fields": (
                    "name",
                    "user_type",
                    "preferred_language",
                    "terms_agreed",
                    "privacy_agreed",
                    "overseas_info_agreed",
                    "marketing_agreed",
                )
            },
        ),
    )

    list_display = (
        "id",
        "username",
        "name",
        "user_type",
        "is_staff",
        "is_active",
    )


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = (
        "patient_id",
        "user",
        "nationality",
        "residence_country",
        "phone",
    )


@admin.register(HospitalProfile)
class HospitalProfileAdmin(admin.ModelAdmin):
    list_display = (
        "hospital_id",
        "user",
        "country",
        "city",
        "hospital_type",
        "phone",
    )


@admin.register(MedicalSpecialty)
class MedicalSpecialtyAdmin(admin.ModelAdmin):
    list_display = (
        "hospital_specialty_id",
        "hospital",
        "specialty_name",
    )
