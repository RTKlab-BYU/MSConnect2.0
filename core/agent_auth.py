from dataclasses import dataclass

from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


@dataclass(frozen=True)
class AgentIdentity:
    agent_role: str
    token_label: str

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return True

    def __str__(self) -> str:
        return f"{self.token_label}:{self.agent_role}"


class AgentTokenAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate_header(self, request) -> str:
        return self.keyword

    def authenticate(self, request):
        authorization = get_authorization_header(request).decode("utf-8")
        if not authorization:
            return None

        keyword, _, token = authorization.partition(" ")
        if keyword != self.keyword:
            return None

        token = token.strip()
        if not token:
            raise AuthenticationFailed("Missing agent bearer token.")

        configured_tokens = [("watcher", "service", settings.MSCONNECT_WATCHER_TOKEN)]
        configured_tokens.extend(
            ("watcher", label, configured_token)
            for label, configured_token in settings.MSCONNECT_WATCHER_TOKENS.items()
        )
        configured_tokens.append(("processor", "service", settings.MSCONNECT_PROCESSOR_TOKEN))
        for role, token_label, configured_token in configured_tokens:
            if configured_token and token == configured_token:
                return AgentIdentity(agent_role=role, token_label=token_label), token

        raise AuthenticationFailed("Invalid agent bearer token.")
