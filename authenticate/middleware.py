from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class JwtAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner
        self.jwt_auth = JWTAuthentication()

    async def __call__(self, scope, receive, send):
        scope["user"] = await self.get_user(scope)
        return await self.inner(scope, receive, send)

    async def get_user(self, scope):
        query_string = scope.get("query_string", b"").decode()
        token = parse_qs(query_string).get("token", [None])[0]
        if not token:
            return scope.get("user", AnonymousUser())

        try:
            validated_token = self.jwt_auth.get_validated_token(token)
        except (InvalidToken, TokenError):
            return scope.get("user", AnonymousUser())

        return await database_sync_to_async(self.jwt_auth.get_user)(validated_token)