from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start_location = serializers.CharField(allow_blank=False, trim_whitespace=True)
    finish_location = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate(self, attrs):
        start = attrs["start_location"].strip()
        finish = attrs["finish_location"].strip()
        if start.casefold() == finish.casefold():
            raise serializers.ValidationError(
                "start_location and finish_location must be different"
            )
        return attrs
