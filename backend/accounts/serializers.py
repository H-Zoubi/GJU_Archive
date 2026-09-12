from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(style={"input_type": "password"}, trim_whitespace=False)


class GjuSyncOptInSerializer(serializers.Serializer):
    """Re-submits the GJU password so it can be encrypted for auto-sync.

    Never persisted or logged as-is -- see accounts.services.opt_in_gju_sync.
    """

    password = serializers.CharField(style={"input_type": "password"}, trim_whitespace=False)


class UserSerializer(serializers.Serializer):
    """Public shape of the logged-in user. Never includes password data."""

    id = serializers.IntegerField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    role = serializers.CharField()
    is_gju_verified = serializers.BooleanField()
    # Drives whether the review dashboard is offered at all.
    can_moderate = serializers.BooleanField(read_only=True)
    # Drives the "my major" default when browsing. Null until known (either
    # picked manually or filled in from MyGJU -- see
    # accounts.services.refresh_profile_from_mygju), in which case the UI
    # falls back to showing every major.
    major = serializers.SerializerMethodField()
    entry_year = serializers.SerializerMethodField()

    def get_major(self, obj):
        profile = getattr(obj, "student_profile", None)
        if profile is None or profile.major is None:
            return None
        return {"slug": profile.major.slug, "name": profile.major.name}

    def get_entry_year(self, obj):
        profile = getattr(obj, "student_profile", None)
        return profile.entry_year if profile is not None else None
