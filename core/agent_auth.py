from dataclasses import dataclass

from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


@dataclass(frozen=True)
class AgentIdentity:
    agent_role: str
    token_label: str
    agent_name: str = ""

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

        # Per-agent secrets are stored as SHA-256 hashes. They are generated with
        # 256 bits of entropy and only shown once by the provisioning endpoint.
        from .agent_tokens import hash_agent_token
        from .models import AcquisitionAgent, ProcessingNode

        token_hash = hash_agent_token(token)
        agent = AcquisitionAgent.objects.filter(
            active=True, provisioning_status="ready", agent_token_hash=token_hash
        ).only("name", "token_label").first()
        if agent:
            return AgentIdentity("watcher", agent.token_label, agent.name), token
        node = ProcessingNode.objects.filter(
            provisioning_status="ready", agent_token_hash=token_hash
        ).only("name").first()
        if node:
            return AgentIdentity("processor", node.name, node.name), token

        raise AuthenticationFailed("Invalid agent bearer token.")
