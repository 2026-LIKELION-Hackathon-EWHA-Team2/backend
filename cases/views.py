from django.shortcuts import render

# Create your views here.
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MedicalCase
from .permissions import IsPatient
from .serializers import (
    AdverseEffectUpdateSerializer,
    CaseTransferSerializer,
    MedicalCaseCreateSerializer,
    MedicalCaseDetailSerializer,
)


class MedicalCaseListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MedicalCaseCreateSerializer

        return MedicalCaseDetailSerializer

    def get_queryset(self):
        user = self.request.user

        if user.user_type == "PATIENT":
            return MedicalCase.objects.filter(
                patient=user
            )

        if user.user_type == "HOSPITAL":
            return MedicalCase.objects.filter(
                Q(origin_hospital=user)
                | Q(
                    partner_hospital=user,
                    status=MedicalCase.Status.TRANSFERRED,
                )
            ).distinct()

        return MedicalCase.objects.none()

    def create(self, request, *args, **kwargs):
        if request.user.user_type != "HOSPITAL":
            raise PermissionDenied(
                "병원 회원만 케이스를 생성할 수 있습니다."
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        medical_case = serializer.save(
            origin_hospital=request.user
        )

        return Response(
            MedicalCaseDetailSerializer(medical_case).data,
            status=status.HTTP_201_CREATED,
        )


class MedicalCaseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, case_id):
        medical_case = get_object_or_404(
            MedicalCase.objects.select_related(
                "patient",
                "origin_hospital",
                "partner_hospital",
            ).prefetch_related(
                "ingredients",
                "adverse_effects",
            ),
            id=case_id,
        )

        is_patient = medical_case.patient == request.user
        is_origin = medical_case.origin_hospital == request.user

        is_partner = (
            medical_case.partner_hospital == request.user
            and medical_case.status
            == MedicalCase.Status.TRANSFERRED
        )

        if not (is_patient or is_origin or is_partner):
            raise PermissionDenied(
                "해당 케이스를 조회할 수 없습니다."
            )

        return Response(
            MedicalCaseDetailSerializer(medical_case).data
        )


class AdverseEffectUpdateView(APIView):
    permission_classes = [IsPatient]

    def put(self, request, case_id):
        medical_case = get_object_or_404(
            MedicalCase,
            id=case_id,
            patient=request.user,
        )

        serializer = AdverseEffectUpdateSerializer(
            data=request.data,
            context={"medical_case": medical_case},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            MedicalCaseDetailSerializer(medical_case).data
        )


class CaseTransferView(APIView):
    permission_classes = [IsPatient]

    def post(self, request, case_id):
        medical_case = get_object_or_404(
            MedicalCase,
            id=case_id,
            patient=request.user,
        )

        serializer = CaseTransferSerializer(
            medical_case,
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            MedicalCaseDetailSerializer(medical_case).data
        )