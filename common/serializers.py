from rest_framework import serializers


class EmptySerializer(serializers.Serializer):
    """Named empty serializer for endpoints without a request body."""

