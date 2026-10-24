"""Read-only HTTP questions to the demo server (GETs only). `httpx` lives here and in
`factory/gate/tts_boson.py` only."""

from urllib.parse import quote

import httpx


class ServerError(Exception):
    """The demo server did not answer a read. The message holds no secret."""


class HttpServer:
    """`ServerPort` over the demo server's GET routes."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _get(self, path: str) -> httpx.Response | None:
        try:
            response = await self._client.get(path)
        except httpx.HTTPError as exc:
            raise ServerError(f"demo server not reachable: {type(exc).__name__}") from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ServerError(f"demo server answered {response.status_code} for {path}")
        return response

    async def latest_run_id(self, agent_id: str) -> str | None:
        response = await self._get(f"/api/agents/{quote(agent_id, safe='')}/card/latest")
        if response is None:
            return None
        run_id = response.json().get("card", {}).get("run_id")
        return run_id if isinstance(run_id, str) else None

    async def coach_pair(self, agent_id: str) -> tuple[str, str] | None:
        response = await self._get(f"/api/agents/{quote(agent_id, safe='')}/coach")
        if response is None:
            return None
        body = response.json()
        before = body.get("before", {}).get("run_id")
        after = body.get("after", {}).get("run_id")
        if isinstance(before, str) and isinstance(after, str):
            return before, after
        return None
