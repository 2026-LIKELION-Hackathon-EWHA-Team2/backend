from django.conf import settings
from django.db import models


class MedicalCase(models.Model):
    class Status(models.TextChoices):
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
        null=True,
        blank=True,
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
        default=Status.READY_TO_TRANSFER,
    )

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
class CaseCollaborationRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "협진 요청"
        ACCEPTED = "ACCEPTED", "협진 수락"
        COMPLETED = "COMPLETED", "협진 완료"
        REJECTED = "REJECTED", "협진 거절"
        CANCELLED = "CANCELLED", "협진 취소"

    medical_case = models.OneToOneField(
        MedicalCase,
        on_delete=models.PROTECT,
        related_name="collaboration_request",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REQUESTED,
    )

    requested_at = models.DateTimeField(
        auto_now_add=True,
    )

    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    rejected_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ("-requested_at",)


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

    source_language = models.CharField(
        max_length=10,
        default="auto",
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


class CaseChatMessageTranslation(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "번역 중"
        COMPLETED = "COMPLETED", "번역 완료"
        FAILED = "FAILED", "번역 실패"

    message = models.ForeignKey(
        CaseChatMessage,
        on_delete=models.PROTECT,
        related_name="translations",
    )

    target_language = models.CharField(
        max_length=10,
    )

    translated_content = models.TextField(
        blank=True,
        default="",
    )

    model_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    error_code = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "message",
                    "target_language",
                ),
                name="unique_message_target_language",
            ),
        ]



class CaseAgreement(models.Model):
    class Status(models.TextChoices):
        AI_DRAFT = "AI_DRAFT", "AI 정리 초안"
        IN_REVIEW = "IN_REVIEW", "의료진 검토 중"
        FINAL = "FINAL", "최종 합의"

    chat_room = models.OneToOneField(
        "CaseChatRoom",
        on_delete=models.PROTECT,
        related_name="agreement",
    )

    judgment_draft = models.TextField()
    evidence_items = models.JSONField(default=list)
    additional_opinion = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AI_DRAFT,
    )
    version = models.PositiveIntegerField(default=1)

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="edited_case_agreements",
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    revision_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="requested_agreement_revisions",
    )
    revision_requested_at = models.DateTimeField(null=True, blank=True)


class CaseAgreementReview(models.Model):
    agreement = models.ForeignKey(
        CaseAgreement,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    hospital = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="case_agreement_reviews",
    )

    reviewed_version = models.PositiveIntegerField()
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("agreement", "hospital"),
                name="unique_agreement_hospital_review",
            ),
        ]


class CaseAgreementRevision(models.Model):
    agreement = models.ForeignKey(
        CaseAgreement,
        on_delete=models.CASCADE,
        related_name="revisions",
    )

    version = models.PositiveIntegerField()
    previous_data = models.JSONField()
    changed_fields = models.JSONField(default=list)

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="case_agreement_revisions",
    )
    edited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-version",)


class CaseTransfer(models.Model):
    medical_case = models.ForeignKey(
        "cases.MedicalCase",
        on_delete=models.PROTECT,
        related_name="case_transfers",
    )

    class Status(models.TextChoices):
        PROCESSING = "PROCESSING", "번역·구조화 중"
        REVIEW_REQUIRED = (
            "REVIEW_REQUIRED",
            "최종 확인 필요",
        )
        PROCESSING_FAILED = (
            "PROCESSING_FAILED",
            "번역·구조화 실패",
        )
        READY_TO_TRANSFER = (
            "READY_TO_TRANSFER",
            "전송 준비 완료",
        )
        TRANSFERRED = "TRANSFERRED", "전송 완료"

    class Gender(models.TextChoices):
        FEMALE = "FEMALE", "여성"
        MALE = "MALE", "남성"
        OTHER = "OTHER", "기타"

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="case_transfers",
    )
    symptom_case = models.ForeignKey(
        "selfsymptoms.PatientSymptomCase",
        on_delete=models.PROTECT,
        related_name="case_transfers",
    )
    recommendation = models.OneToOneField(
        "matching.HospitalRecommendation",
        on_delete=models.PROTECT,
        related_name="case_transfer",
        null=True,
        blank=True,
    )
    partner_hospital = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="received_case_transfers",
    )

    patient_name = models.CharField(max_length=100)
    patient_gender = models.CharField(
        max_length=20,
        choices=Gender.choices,
    )
    patient_birth_date = models.DateField()

    target_language = models.CharField(max_length=10)

    translated_data = models.JSONField(default=dict)
    structured_data = models.JSONField(default=dict)
    processing_error = models.TextField(
        blank=True,
        default="",
    )

    adverse_effects = models.JSONField(default=list)

    include_patient_info = models.BooleanField(default=False)
    include_procedure_info = models.BooleanField(default=False)
    include_adverse_effects = models.BooleanField(default=False)
    include_clinician_note = models.BooleanField(default=False)

    personal_information_provision_agreed = models.BooleanField(
        default=False,
    )
    information_items_purpose_confirmed = models.BooleanField(
        default=False,
    )
    medical_consultation_use_agreed = models.BooleanField(
        default=False,
    )
    withdrawal_right_confirmed = models.BooleanField(
        default=False,
    )
    agreed_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PROCESSING,
    )
    transferred_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("symptom_case",),
                name="unique_symptom_case_transfer",
            ),
        ]
