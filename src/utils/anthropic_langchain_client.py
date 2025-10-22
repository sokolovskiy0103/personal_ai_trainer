"""Anthropic Claude LangChain Client for Personal AI Trainer."""

import logging
from typing import Any, Dict, Iterator, List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.utils.tool_handlers import get_all_tools

logger = logging.getLogger(__name__)


class AnthropicLangChainClient:
    def __init__(
        self,
        api_key: str,
        system_instruction: str,
        model_name: str = "claude-haiku-4-5-20251001",
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ):
        self.api_key = api_key
        self.system_instruction = system_instruction
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.llm = ChatAnthropic(
            model=model_name,
            anthropic_api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        self.tools = get_all_tools()
        self.llm_with_tools = self.llm.bind_tools(self.tools).bind(
            system=[
                {"type": "text", "text": system_instruction, "cache_control": {"type": "ephemeral"}}
            ]
        )
        self.history: List[Any] = []
        logger.info(f"Initialized Claude client with {len(self.tools)} tools")

    @property
    def chat_history(self) -> List[Any]:
        return self.history

    def update_system_instruction(self, user_context: str) -> None:
        updated_instruction = f"{self.system_instruction}\n\n{user_context}"
        self.system_instruction = updated_instruction
        self.llm_with_tools = self.llm.bind_tools(self.tools).bind(
            system=[
                {
                    "type": "text",
                    "text": updated_instruction,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        )

    def start_chat(self, history: Optional[List[Dict[str, str]]] = None) -> None:
        self.history = []
        if history:
            for msg in history:
                if msg["role"] == "user":
                    self.history.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    self.history.append(AIMessage(content=msg["content"]))

    def send_message(self, user_input: str) -> str:
        self.history.append(HumanMessage(content=user_input))

        max_iterations = 10
        for iteration in range(max_iterations):
            response = self.llm_with_tools.invoke(self.history)
            self.history.append(response)

            if hasattr(response, "response_metadata"):
                usage = response.response_metadata.get("usage", {})
                cache_read = usage.get("cache_read_input_tokens", 0)
                if cache_read > 0:
                    logger.info(f"Cache hit: {cache_read} tokens")

            if not response.tool_calls:
                return response.content

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                tool_result = None
                for tool in self.tools:
                    if tool.name == tool_name:
                        try:
                            tool_result = tool.invoke(tool_args)
                        except Exception as e:
                            tool_result = f"ПОМИЛКА при виконанні {tool_name}: {str(e)}"
                            logger.error(f"Tool {tool_name} error: {e}")
                        break

                if tool_result is None:
                    tool_result = f"ПОМИЛКА: Tool {tool_name} не знайдено"

                self.history.append(
                    ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_id,
                    )
                )

        logger.warning(f"Reached max iterations ({max_iterations})")
        return "Вибачте, сталася помилка при обробці запиту. Спробуйте ще раз."

    def send_message_stream(self, user_input: str) -> Iterator[str]:
        self.history.append(HumanMessage(content=user_input))

        max_iterations = 10
        for iteration in range(max_iterations):
            response = self.llm_with_tools.invoke(self.history)
            self.history.append(response)

            if hasattr(response, "response_metadata"):
                usage = response.response_metadata.get("usage", {})
                cache_read = usage.get("cache_read_input_tokens", 0)
                if cache_read > 0:
                    logger.info(f"Cache hit: {cache_read} tokens")

            if not response.tool_calls:
                self.history.pop()

                full_content = ""
                for chunk in self.llm_with_tools.stream(self.history):
                    if chunk.content:
                        if isinstance(chunk.content, str):
                            content_str = chunk.content
                        elif isinstance(chunk.content, list):
                            content_parts = []
                            for item in chunk.content:
                                if isinstance(item, dict) and "text" in item:
                                    content_parts.append(item["text"])
                                elif isinstance(item, str):
                                    content_parts.append(item)
                            content_str = "".join(content_parts)
                        else:
                            content_str = str(chunk.content)

                        if content_str:
                            full_content += content_str
                            yield content_str

                self.history.append(AIMessage(content=full_content))
                return

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                tool_result = None
                for tool in self.tools:
                    if tool.name == tool_name:
                        try:
                            tool_result = tool.invoke(tool_args)
                        except Exception as e:
                            tool_result = f"ПОМИЛКА при виконанні {tool_name}: {str(e)}"
                            logger.error(f"Tool {tool_name} error: {e}")
                        break

                if tool_result is None:
                    tool_result = f"ПОМИЛКА: Tool {tool_name} не знайдено"

                self.history.append(
                    ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_id,
                    )
                )

        logger.warning(f"Reached max iterations ({max_iterations})")
        yield "Вибачте, сталася помилка при обробці запиту. Спробуйте ще раз."

    def get_history(self) -> List[Dict[str, str]]:
        simple_history = []
        for msg in self.history:
            if isinstance(msg, HumanMessage):
                simple_history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage) and msg.content:
                simple_history.append({"role": "assistant", "content": msg.content})
        return simple_history
