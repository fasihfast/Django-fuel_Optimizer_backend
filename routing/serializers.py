from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    """
    Validates the incoming request body.

    """

    start = serializers.CharField(
        max_length=255,
        help_text='Start location, e.g. "Chicago, IL" or a full street address.',
    )
    finish = serializers.CharField(
        max_length=255,
        help_text='Destination location, e.g. "Denver, CO".',
    )
