from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User

from rest_framework_simplejwt.tokens import RefreshToken

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(max_length=128, write_only=True,)

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'password'
        )

    def create(self, validated_data):
        user = User.objects.create(
            username=validated_data['username'],
            email=validated_data['email']
        )

        user.set_password(validated_data['password'])
        user.save()

        return user


class UserLoginSerializer(serializers.Serializer):
    email = serializers.CharField(max_length=100)
    password = serializers.CharField(max_length=128, write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if not User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                {"detail": "이메일 또는 비밀번호가 올바르지 않습니다."}
            )

        user = User.objects.get(email=email)

        if not user.check_password(password):
            raise serializers.ValidationError(
                {"detail": "이메일 또는 비밀번호가 올바르지 않습니다."}
            )

        token = RefreshToken.for_user(user)

        return {
            'id' :user.id,
            'email': user.email,                
            "access": str(token.access_token),
            "refresh": str(token),
       }