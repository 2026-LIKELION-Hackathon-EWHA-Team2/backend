from rest_framework import serializers

from ..models import (
    CaseAgreement,
    CaseChatMessage,
    CaseChatRoom,
    CaseCollaborationRequest,
)
from .transfers import format_medical_case_number


class CaseChatMessageSerializer(serializers.ModelSerializer):
    sender_hospital_id = serializers.IntegerField(
        source="sender.id",
        read_only=True,
    )

    sender_hospital_name = serializers.CharField(
        source="sender.name",
        read_only=True,
    )

    translated_content = serializers.SerializerMethodField()
    translation_status = serializers.SerializerMethodField()
    display_content = serializers.SerializerMethodField()

    content = serializers.CharField(
        max_length=4000,
        trim_whitespace=True,
        error_messages={
            "required": "메시지 내용을 입력해 주세요.",
            "blank": "메시지 내용을 입력해 주세요.",
            "max_length": (
                "메시지는 4,000자 이하로 입력해 주세요."
            ),
        },
    )

    class Meta:
        model = CaseChatMessage
        fields = (
            "id",
            "sender_hospital_id",
            "sender_hospital_name",
            "content",
            "source_language",
            "translated_content",
            "translation_status",
            "display_content",
            "created_at",
        )
        read_only_fields = (
            "id",
            "sender_hospital_id",
            "sender_hospital_name",
            "source_language",
            "translated_content",
            "translation_status",
            "display_content",
            "created_at",
        )

    def get_selected_translation(self, obj):
        request = self.context.get("request")

        if request is None:
            return None

        if obj.sender_id == request.user.id:
            return None

        target_language = (
            request.user.preferred_language
        )

        return next(
            (
                translation
                for translation
                in obj.translations.all()
                if translation.target_language
                == target_language
            ),
            None,
        )

    def get_translated_content(self, obj):
        translation = self.get_selected_translation(obj)

        if (
            translation is not None
            and translation.status == "COMPLETED"
        ):
            return translation.translated_content

        return None

    def get_translation_status(self, obj):
        translation = self.get_selected_translation(obj)

        if translation is None:
            return None

        return translation.status

    def get_display_content(self, obj):
        translated_content = (
            self.get_translated_content(obj)
        )

        return translated_content or obj.content


class CaseChatRoomListSerializer(serializers.ModelSerializer):
    class ChatStatus:
        IN_REVIEW = "IN_REVIEW"
        COMPLETED = "COMPLETED"

    room_id = serializers.IntegerField(source="id", read_only=True)
    medical_case_id = serializers.IntegerField(read_only=True)
    case_number = serializers.SerializerMethodField()
    patient_id = serializers.IntegerField(
        source="medical_case.patient.id",
        read_only=True,
    )
    patient_name = serializers.CharField(
        source="medical_case.patient.name",
        read_only=True,
    )
    procedure_name = serializers.CharField(
        source="medical_case.procedure_name",
        read_only=True,
    )
    origin_hospital_id = serializers.IntegerField(
        source="medical_case.origin_hospital.id",
        read_only=True,
    )
    origin_hospital_name = serializers.CharField(
        source="medical_case.origin_hospital.name",
        read_only=True,
    )
    partner_hospital_id = serializers.IntegerField(read_only=True)
    partner_hospital_name = serializers.CharField(
        source="partner_hospital.name",
        read_only=True,
    )
    counterpart_hospital_id = serializers.SerializerMethodField()
    counterpart_hospital_name = serializers.SerializerMethodField()
    collaboration_request_id = serializers.SerializerMethodField()
    collaboration_request_status = serializers.SerializerMethodField()
    agreement_id = serializers.SerializerMethodField()
    agreement_status = serializers.SerializerMethodField()
    agreement_finalized_at = serializers.SerializerMethodField()
    chat_status = serializers.SerializerMethodField()
    chat_status_label = serializers.SerializerMethodField()
    can_view_agreement = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_message_at = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = CaseChatRoom
        fields = (
            "room_id",
            "medical_case_id",
            "case_number",
            "patient_id",
            "patient_name",
            "procedure_name",
            "origin_hospital_id",
            "origin_hospital_name",
            "partner_hospital_id",
            "partner_hospital_name",
            "counterpart_hospital_id",
            "counterpart_hospital_name",
            "collaboration_request_id",
            "collaboration_request_status",
            "agreement_id",
            "agreement_status",
            "agreement_finalized_at",
            "chat_status",
            "chat_status_label",
            "can_view_agreement",
            "last_message",
            "last_message_at",
            "unread_count",
            "created_at",
        )
        read_only_fields = fields

    def get_case_number(self, obj):
        return format_medical_case_number(obj.medical_case)

    def get_counterpart_hospital(self, obj):
        request = self.context["request"]
        if request.user.id == obj.partner_hospital_id:
            return obj.medical_case.origin_hospital
        return obj.partner_hospital

    def get_counterpart_hospital_id(self, obj):
        return self.get_counterpart_hospital(obj).id

    def get_counterpart_hospital_name(self, obj):
        return self.get_counterpart_hospital(obj).name

    def get_collaboration_request(self, obj):
        try:
            return obj.medical_case.collaboration_request
        except CaseCollaborationRequest.DoesNotExist:
            return None

    def get_collaboration_request_id(self, obj):
        collaboration_request = self.get_collaboration_request(obj)
        return collaboration_request.id if collaboration_request else None

    def get_collaboration_request_status(self, obj):
        collaboration_request = self.get_collaboration_request(obj)
        return collaboration_request.status if collaboration_request else None

    @staticmethod
    def get_agreement(obj):
        try:
            agreement = obj.agreement
        except CaseAgreement.DoesNotExist:
            return None

        if agreement.status != CaseAgreement.Status.FINAL:
            return None
        return agreement

    def get_agreement_id(self, obj):
        agreement = self.get_agreement(obj)
        return agreement.id if agreement else None

    def get_agreement_status(self, obj):
        agreement = self.get_agreement(obj)
        return agreement.status if agreement else None

    def get_agreement_finalized_at(self, obj):
        agreement = self.get_agreement(obj)
        if agreement is None or agreement.finalized_at is None:
            return None
        return serializers.DateTimeField().to_representation(
            agreement.finalized_at
        )

    def get_chat_status(self, obj):
        agreement = self.get_agreement(obj)
        if agreement and agreement.status == CaseAgreement.Status.FINAL:
            return self.ChatStatus.COMPLETED
        return self.ChatStatus.IN_REVIEW

    def get_chat_status_label(self, obj):
        if self.get_chat_status(obj) == self.ChatStatus.COMPLETED:
            return "완료"
        return "검토중"

    def get_can_view_agreement(self, obj):
        return self.get_agreement(obj) is not None

    def get_messages(self, obj):
        return getattr(obj, "chat_list_messages", [])

    def get_last_message(self, obj):
        messages = self.get_messages(obj)
        if not messages:
            return None

        return CaseChatMessageSerializer(
            messages[-1],
            context=self.context,
        ).data

    def get_last_message_at(self, obj):
        messages = self.get_messages(obj)
        return messages[-1].created_at if messages else None

    def get_unread_count(self, obj):
        request = self.context["request"]
        read_states = getattr(obj, "viewer_read_states", [])
        last_read_message_id = (
            read_states[0].last_read_message_id
            if read_states
            else None
        )

        return sum(
            1
            for message in self.get_messages(obj)
            if message.sender_id != request.user.id
            and (
                last_read_message_id is None
                or message.id > last_read_message_id
            )
        )
