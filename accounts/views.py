from django.http import HttpRequest
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import UserSerializer, UserLoginSerializer

class SignUpView(APIView):
    def post(self, request:HttpRequest, format=None):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    def post(self, request:HttpRequest, format=None):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: HttpRequest, format=None):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response(
                {"detail": "refresh token이 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(
                {"detail": "로그아웃되었습니다."},
                status=status.HTTP_200_OK,
            )

        except TokenError:
            return Response(
                {"detail": "유효하지 않거나 만료된 refresh token입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )