from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User

        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "avatar",
            "role",
            "is_verified",
            "created_at",
        )

        read_only_fields = (
            "id",
            "username",
            "email",
            "role",
            "is_verified",
            "created_at",
        )


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token["username"] = user.username
        token["role"] = user.role

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        data["user"] = UserSerializer(
            self.user,
            context=self.context,
        ).data

        return data


class RegisterSerializer(serializers.ModelSerializer):

    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        validators=[validate_password],
    )

    class Meta:
        model = User

        fields = (
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
        )

    def validate_email(self, value):
        normalized_email = value.strip().lower()

        if User.objects.filter(
            email__iexact=normalized_email
        ).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )

        return normalized_email

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )


class UserListSerializer(serializers.ModelSerializer):

    class Meta:
        model = User

        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "is_active",
        )


class UserRoleUpdateSerializer(serializers.Serializer):

    role = serializers.ChoiceField(
        choices=User.Role.choices,
    )


class ProfileUpdateSerializer(serializers.ModelSerializer):

    phone = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=20,
    )

    class Meta:
        model = User

        fields = (
            "first_name",
            "last_name",
            "phone",
            "avatar",
        )

        extra_kwargs = {
            "first_name": {
                "required": False,
            },
            "last_name": {
                "required": False,
            },
            "avatar": {
                "required": False,
                "allow_null": True,
            },
        }

    def validate_phone(self, value):
        if value in (None, ""):
            return None

        normalized_phone = value.strip()

        queryset = User.objects.filter(
            phone=normalized_phone
        )

        if self.instance:
            queryset = queryset.exclude(
                pk=self.instance.pk
            )

        if queryset.exists():
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )

        return normalized_phone

    def validate_avatar(self, value):
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError(
                "Avatar size cannot exceed 5 MB."
            )

        return value