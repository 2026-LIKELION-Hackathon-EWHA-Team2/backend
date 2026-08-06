from django.conf import settings
from django.db import models


class MedicalCase(models.Model):
    class Status(models.TextChoices):
        WAITING_PATIENT = (
            "WAITING_PATIENT",
            "환자 확인 대기",
        )
        READY_TO_TRANSFER = (
            "READY_TO_TRANSFER",
            "전송 동의 대기",
        )
        TRANSFERRED = (
            "TRANSFERRED",
            "전송 완료",
        )

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patient_cases",
    )

    origin_hospital = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_cases",
    )

    # AI 추천 후 매칭된 병원
    partner_hospital = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_cases",
    )

    # 시술 정보
    procedure_name = models.CharField(max_length=150)
    procedure_area = models.CharField(max_length=100)
    procedure_date = models.DateField()

    # 의료진 자유 소견
    clinician_note = models.TextField()

    # 추후 AI 요약 기능 연결
    ai_summary = models.TextField(
        blank=True,
        default="",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.WAITING_PATIENT,
    )

    # 환자의 전송 동의
    procedure_info_agreed = models.BooleanField(default=False)
    adverse_effect_info_agreed = models.BooleanField(default=False)
    overseas_transfer_agreed = models.BooleanField(default=False)

    transferred_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CaseIngredient(models.Model):
    medical_case = models.ForeignKey(
        MedicalCase,
        on_delete=models.CASCADE,
        related_name="ingredients",
    )

    ingredient_name = models.CharField(max_length=150)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["medical_case", "ingredient_name"],
                name="unique_case_ingredient",
            )
        ]


class CaseAdverseEffect(models.Model):
    class EffectType(models.TextChoices):
        SWELLING = "SWELLING", "부종"
        INFLAMMATION = "INFLAMMATION", "염증"
        PAIN = "PAIN", "통증"
        REDNESS = "REDNESS", "붉어짐"
        INFECTION = "INFECTION", "감염 의심"
        PIGMENTATION = "PIGMENTATION", "색소침착"

    medical_case = models.ForeignKey(
        MedicalCase,
        on_delete=models.CASCADE,
        related_name="adverse_effects",
    )

    effect_type = models.CharField(
        max_length=30,
        choices=EffectType.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["medical_case", "effect_type"],
                name="unique_case_adverse_effect",
            )
        ]


class CaseChatRoom(models.Model):
    medical_case = models.ForeignKey(
        MedicalCase,
        on_delete=models.PROTECT,
        related_name="chat_rooms",
    )

    partner_hospital = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="partner_chat_rooms",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "medical_case",
                    "partner_hospital",
                ),
                name="unique_case_partner_chat_room",
            ),
        ]


class CaseChatMessage(models.Model):
    chat_room = models.ForeignKey(
        CaseChatRoom,
        on_delete=models.PROTECT,
        related_name="messages",
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sent_case_chat_messages",
    )

    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)
        indexes = [
            models.Index(
                fields=("chat_room", "id"),
                name="chat_room_message_idx",
            ),
        ]