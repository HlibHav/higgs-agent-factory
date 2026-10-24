"""Anthropic `CoachModel` adapter. Client (max_retries=0) and model id come from the root."""

from factory.agent_spec.brief_anthropic import MessagesClient

_MAX_TOKENS = 1024


class AnthropicCoachModel:
    def __init__(self, client: MessagesClient, model_id: str) -> None:
        self._client = client
        self._model_id = model_id

    async def rewrite_procedure(self, prompt: str) -> str:
        response = await self._client.messages.create(
            model=self._model_id,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
