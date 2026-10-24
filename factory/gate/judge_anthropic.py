"""Anthropic adapter for `JudgePort`: the only place the judge talks to the SDK."""

import anthropic

from factory.gate.judge import build_judge_prompt
from factory.ports import JudgeRequest

_MAX_TOKENS = 1024


class AnthropicJudge:
    """Sends one message per scenario. `model_id` comes from the composition root.

    No retries (spec NFR Reliability): the client is copied with `max_retries=0` whatever the
    caller configured.
    """

    def __init__(self, client: anthropic.AsyncAnthropic, model_id: str) -> None:
        self._client = client.with_options(max_retries=0)
        self._model_id = model_id

    async def judge(self, request: JudgeRequest) -> str:
        message = await self._client.messages.create(
            model=self._model_id,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": build_judge_prompt(request)}],
        )
        return "".join(block.text for block in message.content if block.type == "text")
