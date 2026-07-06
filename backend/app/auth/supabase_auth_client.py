"""Server-to-server Supabase GoTrue client (BFF: the browser never talks to GoTrue).

Built in the composition root with an injected httpx.AsyncClient carrying
EXPLICIT timeouts — never constructed at import time. All methods return typed
DTOs and map provider failures to OAuthExchangeError; raw JSON and raw tokens
never leak upward. Token values ride in SecretStr so accidental logging/repr
cannot expose them.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from app.auth.exceptions import OAuthExchangeError

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


class GoTrueTokenSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    access_token: SecretStr
    refresh_token: SecretStr
    expires_in: int = 3600
    token_type: str = "bearer"


class GoTrueUser(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str  # the GoTrue subject (sub)
    email: str | None = None


class SupabaseAuthClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        project_url: str,
        anon_key: str,
        redirect_uri: str,
        provider: str,
    ) -> None:
        self._http = http_client
        self._base = project_url.rstrip("/") + "/auth/v1"
        self._anon_key = anon_key
        self._redirect_uri = redirect_uri
        self._provider = provider

    def build_authorize_url(self, *, code_challenge: str, state: str) -> str:
        query = urlencode(
            {
                "provider": self._provider,
                "redirect_to": self._redirect_uri,
                "response_type": "code",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
        )
        return f"{self._base}/authorize?{query}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> GoTrueTokenSet:
        """Exchange the authorization code + PKCE verifier for a token set.

        The body/endpoint shape is deliberately isolated HERE and nowhere else.
        """
        # TODO(verify): confirm PKCE token-exchange body against the deployed
        # GoTrue version (supabase-js sends POST /token?grant_type=pkce with
        # {"auth_code": ..., "code_verifier": ...}; older/newer GoTrue builds
        # may differ).
        payload = {"auth_code": code, "code_verifier": code_verifier}
        data = await self._post_json("/token?grant_type=pkce", json=payload)
        return GoTrueTokenSet(**data)

    async def refresh(self, *, refresh_token: str) -> GoTrueTokenSet:
        data = await self._post_json(
            "/token?grant_type=refresh_token", json={"refresh_token": refresh_token}
        )
        return GoTrueTokenSet(**data)

    async def logout(self, *, access_token: str) -> None:
        await self._request(
            "POST",
            "/logout",
            headers={"Authorization": f"Bearer {access_token}"},
            expect_json=False,
        )

    async def get_user(self, *, access_token: str) -> GoTrueUser:
        data = await self._request(
            "GET", "/user", headers={"Authorization": f"Bearer {access_token}"}
        )
        return GoTrueUser(**data)

    async def _post_json(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, json=json)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expect_json: bool = True,
    ) -> dict[str, Any]:
        request_headers = {"apikey": self._anon_key}
        if headers:
            request_headers.update(headers)
        try:
            response = await self._http.request(
                method, f"{self._base}{path}", json=json, headers=request_headers
            )
        except httpx.HTTPError as exc:
            raise OAuthExchangeError(
                details={"error_type": type(exc).__name__, "operation": path.split("?")[0]}
            ) from exc
        if response.status_code >= 400:
            # GoTrue error bodies carry {error, error_description} or {msg};
            # expose only the status + provider code, never token material.
            raise OAuthExchangeError(details=_safe_error_details(response, path))
        if not expect_json:
            return {}
        body = response.json()
        return body if isinstance(body, dict) else {}


def _safe_error_details(response: httpx.Response, path: str) -> dict[str, Any]:
    provider_code: str | None = None
    try:
        body = response.json()
        if isinstance(body, dict):
            raw = body.get("error_code") or body.get("error") or body.get("msg")
            provider_code = str(raw) if raw is not None else None
    except ValueError:
        provider_code = None
    return {
        "status": response.status_code,
        "provider_code": provider_code,
        "operation": path.split("?")[0],
    }
