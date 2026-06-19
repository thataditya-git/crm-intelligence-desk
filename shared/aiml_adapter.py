"""
Adapter wrapper — supports Azure OpenAI, AI/ML API, or direct Anthropic API.
Set the appropriate env vars to select the provider.
"""

from __future__ import annotations

import json as _json
import logging
import os
from typing import Any

from openai import AsyncAzureOpenAI

from band.adapters.anthropic import AnthropicAdapter

logger = logging.getLogger(__name__)


class _AzureToolUseBlock:
    """Mimics Anthropic ToolUseBlock for Azure tool calls."""
    def __init__(self, tool_call):
        self.type = "tool_use"
        self.id = tool_call.id
        self.name = tool_call.function.name
        try:
            self.input = _json.loads(tool_call.function.arguments or "{}")
        except Exception:
            self.input = {}


class _AzureTextBlock:
    """Mimics Anthropic TextBlock."""
    def __init__(self, text):
        self.type = "text"
        self.text = text or ""


class _AzureResponseWrapper:
    """Wraps Azure OpenAI response to look like an Anthropic Message."""
    def __init__(self, resp):
        choice = resp.choices[0]
        msg = choice.message

        self.content = []
        if msg.content:
            self.content.append(_AzureTextBlock(msg.content))
        if msg.tool_calls:
            for tc in msg.tool_calls:
                self.content.append(_AzureToolUseBlock(tc))

        self.stop_reason = "tool_use" if msg.tool_calls else "end_turn"


class AIMLAnthropicAdapter(AnthropicAdapter):
    """
    Adapter that routes LLM calls based on available env vars:
    - AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT → Azure OpenAI
    - AIML_API_KEY → AI/ML API
    - ANTHROPIC_API_KEY → direct Anthropic API
    """

    def __init__(self, **kwargs):
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        aiml_key = os.getenv("AIML_API_KEY")

        if "provider_key" not in kwargs and not aiml_key and not os.getenv("ANTHROPIC_API_KEY"):
            kwargs["provider_key"] = azure_key or "placeholder"
        elif aiml_key and "provider_key" not in kwargs:
            kwargs["provider_key"] = aiml_key

        super().__init__(**kwargs)

        if azure_key and azure_endpoint:
            self._azure_client = AsyncAzureOpenAI(
                api_key=azure_key,
                azure_endpoint=azure_endpoint,
                api_version="2024-12-01-preview",
            )
            self._azure_deployment = azure_deployment
            self._use_azure = True
        elif aiml_key:
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(
                api_key=aiml_key,
                base_url="https://api.aimlapi.com",
            )
            self._use_azure = False
        else:
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            self._use_azure = False

    async def _call_anthropic(self, messages, tools):
        if not getattr(self, "_use_azure", False):
            return await super()._call_anthropic(messages, tools)

        oai_messages = [{"role": "system", "content": self._system_prompt}]
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        btype = block.get("type")
                    else:
                        btype = getattr(block, "type", None)

                    if btype == "tool_use":
                        bid = block["id"] if isinstance(block, dict) else block.id
                        bname = block["name"] if isinstance(block, dict) else block.name
                        binput = block["input"] if isinstance(block, dict) else block.input
                        oai_messages.append({
                            "role": "assistant",
                            "tool_calls": [{
                                "id": bid,
                                "type": "function",
                                "function": {
                                    "name": bname,
                                    "arguments": _json.dumps(binput),
                                }
                            }]
                        })
                    elif btype == "tool_result":
                        tid = block["tool_use_id"] if isinstance(block, dict) else block.get("tool_use_id", "")
                        tcontent = block["content"] if isinstance(block, dict) else block.get("content", "")
                        oai_messages.append({
                            "role": "tool",
                            "tool_call_id": tid,
                            "content": tcontent if isinstance(tcontent, str) else _json.dumps(tcontent),
                        })
                    elif btype == "text":
                        btext = block["text"] if isinstance(block, dict) else block.text
                        oai_messages.append({"role": role, "content": btext})
            else:
                oai_messages.append({"role": role, "content": content})

        oai_tools = []
        for t in (tools or []):
            if isinstance(t, dict):
                oai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    }
                })

        is_reasoning = self._azure_deployment.startswith(("o1", "o3", "o4"))
        token_key = "max_completion_tokens" if is_reasoning else "max_tokens"
        call_kwargs: dict[str, Any] = {
            "model": self._azure_deployment,
            "messages": oai_messages,
            token_key: self.max_tokens,
        }
        if oai_tools:
            call_kwargs["tools"] = oai_tools

        logger.debug("Azure call with %d messages, %d tools", len(oai_messages), len(oai_tools))
        resp = await self._azure_client.chat.completions.create(**call_kwargs)
        return _AzureResponseWrapper(resp)

    # --- Override isinstance-based methods to handle Azure block types ---

    def _extract_text_content(self, content: list) -> str:
        """Extract text from both Anthropic and Azure block types."""
        texts = []
        for block in content:
            if hasattr(block, "type") and block.type == "text" and hasattr(block, "text") and block.text:
                texts.append(block.text)
        return " ".join(texts) if texts else ""

    def _serialize_content_blocks(self, content: list) -> list[dict]:
        """Serialize both Anthropic and Azure block types to dict format."""
        serialized = []
        for block in content:
            btype = getattr(block, "type", None)
            if btype == "tool_use":
                serialized.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
            elif btype == "text" and block.text:
                serialized.append({
                    "type": "text",
                    "text": block.text,
                })
        return serialized

    async def _process_tool_calls(self, response, tools) -> list[dict]:
        """Process tool_use blocks from both Anthropic and Azure responses."""
        import json
        tool_results = []

        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            tool_use_id = block.id

            logger.debug("Executing tool: %s with input: %s", tool_name, tool_input)

            try:
                from band.runtime.custom_tools import execute_custom_tool, find_custom_tool
                custom_tool = find_custom_tool(self._custom_tools, tool_name)
                if custom_tool:
                    result = await execute_custom_tool(custom_tool, tool_input)
                else:
                    result = await tools.execute_tool_call(tool_name, tool_input)
                result_str = (
                    json.dumps(result, default=str)
                    if not isinstance(result, str)
                    else result
                )
                is_error = False
            except Exception as e:
                result_str = f"Error: {e}"
                is_error = True
                logger.error("Tool %s failed: %s", tool_name, e)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result_str,
                "is_error": is_error,
            })

        return tool_results
