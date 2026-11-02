"""Google sign-in: OpenID Connect, code flow.

The id token comes straight from Google's token endpoint over TLS, so its
claims are read without a signature check.
"""

import base64
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlencode

import httpx
from stario.json import loads

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True, slots=True)
class Google:
    http: httpx.AsyncClient
    client_id: str
    client_secret: str

    def auth_url(self, redirect_uri: str, state: str) -> str:
        query = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email",
            "state": state,
            "prompt": "select_account",
        }
        return f"{AUTH}?{urlencode(query)}"

    async def email(self, code: str, redirect_uri: str) -> str | None:
        """The verified email of the account that signed in, or None."""
        r = await self.http.post(
            TOKEN,
            data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if r.status_code != 200:
            return None
        parts = str(r.json().get("id_token", "")).split(".")
        if len(parts) != 3:
            return None
        claims = cast(dict[str, Any], loads(base64.urlsafe_b64decode(parts[1] + "==")))
        if claims.get("aud") != self.client_id or claims.get("email_verified") is not True:
            return None
        return str(claims.get("email", "")).lower() or None
