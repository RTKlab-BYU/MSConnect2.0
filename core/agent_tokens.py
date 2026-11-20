"""Issue and validate high-entropy tokens for individually provisioned agents."""

import hashlib
import secrets


def issue_agent_token() -> str:
    return secrets.token_urlsafe(32)


def hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
