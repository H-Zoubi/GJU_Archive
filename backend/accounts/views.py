from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import gju_verifier
from .serializers import LoginSerializer, UserSerializer

User = get_user_model()
MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"


def _is_gju_email(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in [d.lower() for d in settings.GJU_EMAIL_DOMAINS]


class LoginView(APIView):
    """
    Sign in only — there is no separate sign-up.

    - Known email: authenticate against the stored password hash (Django auth).
    - Unknown GJU email: verify the credentials against MyGJU, then create the
      account on the spot and log in. The first password entered becomes the
      stored hash.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        password = serializer.validated_data["password"]

        user = User.objects.filter(email=email).first()

        if user is None:
            # Unknown email: this is the signup path, so it's gated to real GJU
            # addresses. Existing accounts (e.g. admins/superadmins created via
            # `createsuperuser`, who may not have a @gju.edu.jo email) skip this
            # gate entirely and go straight to the password check below.
            if not _is_gju_email(email):
                return Response(
                    {"detail": "Please use your GJU email address."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # First time we see this email: prove it's a real GJU account by
            # logging into MyGJU with these credentials.
            result = gju_verifier.verify(email, password)
            if result == "wrong":
                return Response(
                    {"detail": "Incorrect email or password."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if result == "unavailable":
                # We couldn't reach a verdict (portal down / blocking us). Fail
                # closed rather than admit an unverified account. TODO: fall
                # back to email-link verification here (see tech-plan) so signup
                # still works when GJU is unreachable.
                return Response(
                    {
                        "detail": "We couldn't verify your GJU account right now. "
                        "Please try again in a few minutes."
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            # result == "ok": credentials accepted by MyGJU.
            user = User.objects.create_user(email=email, password=password)
            # Passing the GJU check is what unlocks downloads and uploads.
            user.is_gju_verified = True
            user.save(update_fields=["is_gju_verified"])
            django_login(request, user, backend=MODEL_BACKEND)
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

        # Known email: normal password check against our stored hash.
        auth_user = authenticate(request, username=email, password=password)
        if auth_user is None:
            return Response(
                {"detail": "Incorrect email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if auth_user.is_banned:
            return Response(
                {"detail": "This account has been banned."},
                status=status.HTTP_403_FORBIDDEN,
            )
        django_login(request, auth_user)
        return Response(UserSerializer(auth_user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        django_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Current user, or 401 if not signed in. Frontend uses this to know state."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """Sets the csrftoken cookie so the SPA can send X-CSRFToken on writes."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"detail": "CSRF cookie set."})
