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
        """
        Initialize Claude client with LangChain.

        Args:
            api_key: Anthropic API key
            system_instruction: System prompt for the AI trainer
            model_name: Claude model to use (default: claude-haiku-4-5-20251001)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
        """
        self.api_key = api_key
        self.system_instruction = system_instruction
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Initialize LangChain ChatAnthropic
        self.llm = ChatAnthropic(
            model=model_name,
            anthropic_api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Get all tools
        self.tools = get_all_tools()

        # Bind tools AND system prompt with caching
        # This is the KEY for prompt caching to work!
        self.llm_with_tools = self.llm.bind_tools(self.tools).bind(
            system=[
                {
                    "type": "text",
                    "text": system_instruction,
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        )

        # History contains ONLY user/assistant/tool messages (NO system message)
        self.history: List[Any] = []

        logger.info(f"Initialized Claude client with model: {model_name}")
        logger.info(f"Bound {len(self.tools)} tools to LLM")
        logger.info("System prompt configured with prompt caching (90% cost reduction)")

    @property
    def chat_history(self) -> List[Any]:
        """Get chat history for compatibility with app.py."""
        return self.history

    def update_system_instruction(self, user_context: str) -> None:
        """
        Update system instruction with user context.

        IMPORTANT: This should be called ONCE at initialization with user context.
        DO NOT call this repeatedly during conversation as it invalidates the cache!

        For caching to work, the total system prompt must be >4096 tokens.

        Args:
            user_context: Additional context about user (profile, plan, etc.)
        """
        # Append user context to system instruction
        updated_instruction = f"{self.system_instruction}\n\n{user_context}"
        self.system_instruction = updated_instruction

        # Re-bind with updated system prompt (with caching)
        self.llm_with_tools = self.llm.bind_tools(self.tools).bind(
            system=[
                {
                    "type": "text",
                    "text": updated_instruction,
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        )

        logger.info(f"Updated system instruction (length: {len(updated_instruction)} chars)")
        logger.info("System prompt will be cached if >4096 tokens")

    def start_chat(self, history: Optional[List[Dict[str, str]]] = None) -> None:
        """
        Start a new chat session with optional history.

        Args:
            history: Previous conversation history in format:
                    [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        """
        # Clear history - system prompt is NOT in history anymore!
        self.history = []

        # Convert history to LangChain messages (NO SystemMessage!)
        if history:
            for msg in history:
                if msg["role"] == "user":
                    self.history.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    self.history.append(AIMessage(content=msg["content"]))

        logger.info(f"Started chat with {len(self.history)} messages in history")
        logger.info("System prompt will be cached (90% cost reduction for cached tokens)")

    def send_message(self, user_input: str) -> str:
        """
        Send a message and get response, handling tool calls automatically.

        Args:
            user_input: User's message

        Returns:
            Final text response after all tool executions
        """
        # Add user message to history
        self.history.append(HumanMessage(content=user_input))

        # Multi-turn conversation with tool calling
        max_iterations = 10
        for iteration in range(max_iterations):
            # Get LLM response with system prompt from .bind()
            # System prompt is passed automatically via .bind(system=[...])
            response = self.llm_with_tools.invoke(self.history)
            self.history.append(response)

            # Log cache usage from response metadata
            if hasattr(response, 'response_metadata'):
                usage = response.response_metadata.get('usage', {})
                logger.info(f"Usage stats: {usage}")
                cache_read = usage.get('cache_read_input_tokens', 0)
                cache_created = usage.get('cache_creation_input_tokens', 0)
                if cache_read > 0:
                    logger.info(f"✓ CACHE HIT: {cache_read} tokens read from cache!")
                if cache_created > 0:
                    logger.info(f"✓ CACHE CREATED: {cache_created} tokens cached")
            else:
                logger.warning("No response_metadata in response!")

            # Check if there are tool calls
            if not response.tool_calls:
                # No tool calls - this is the final response
                return response.content

            # Execute tool calls
            logger.info(f"Iteration {iteration + 1}: Processing {len(response.tool_calls)} tool calls")

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                logger.info(f"Executing tool: {tool_name} with args: {tool_args}")

                # Find and execute the tool
                tool_result = None
                for tool in self.tools:
                    if tool.name == tool_name:
                        try:
                            tool_result = tool.invoke(tool_args)
                            logger.info(f"Tool {tool_name} result: {tool_result}")
                        except Exception as e:
                            tool_result = f"ПОМИЛКА при виконанні {tool_name}: {str(e)}"
                            logger.error(f"Tool {tool_name} error: {e}", exc_info=True)
                        break

                if tool_result is None:
                    tool_result = f"ПОМИЛКА: Tool {tool_name} не знайдено"
                    logger.error(f"Tool {tool_name} not found in available tools")

                # Add tool result to history
                self.history.append(ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_id,
                ))

        # Safety limit reached
        logger.warning(f"Reached max iterations ({max_iterations}) for tool calling")
        return "Вибачте, сталася помилка при обробці запиту. Спробуйте ще раз."

    def send_message_stream(self, user_input: str) -> Iterator[str]:
        """
        Send a message and stream response, handling tool calls automatically.

        Args:
            user_input: User's message

        Yields:
            Chunks of text response as they are generated
        """
        # Add user message to history
        self.history.append(HumanMessage(content=user_input))

        # Multi-turn conversation with tool calling
        max_iterations = 10
        for iteration in range(max_iterations):
            # Check if this iteration needs tool calls or can stream
            # First, get response to check for tool calls
            response = self.llm_with_tools.invoke(self.history)
            self.history.append(response)

            # Log cache usage from response metadata
            if hasattr(response, 'response_metadata'):
                usage = response.response_metadata.get('usage', {})
                logger.info(f"Usage stats: {usage}")
                cache_read = usage.get('cache_read_input_tokens', 0)
                cache_created = usage.get('cache_creation_input_tokens', 0)
                if cache_read > 0:
                    logger.info(f"✓ CACHE HIT: {cache_read} tokens read from cache!")
                if cache_created > 0:
                    logger.info(f"✓ CACHE CREATED: {cache_created} tokens cached")
            else:
                logger.warning("No response_metadata in response!")

            # Check if there are tool calls
            if not response.tool_calls:
                # No tool calls - stream the final response
                # Remove the non-streamed response from history
                self.history.pop()

                # Stream the response
                full_content = ""
                for chunk in self.llm_with_tools.stream(self.history):
                    if chunk.content:
                        # Handle different content types
                        if isinstance(chunk.content, str):
                            content_str = chunk.content
                        elif isinstance(chunk.content, list):
                            # Extract text from list of dicts or strings
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

                # Add complete response to history
                self.history.append(AIMessage(content=full_content))
                return

            # Execute tool calls (non-streaming part)
            logger.info(f"Iteration {iteration + 1}: Processing {len(response.tool_calls)} tool calls")

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                logger.info(f"Executing tool: {tool_name} with args: {tool_args}")

                # Find and execute the tool
                tool_result = None
                for tool in self.tools:
                    if tool.name == tool_name:
                        try:
                            tool_result = tool.invoke(tool_args)
                            logger.info(f"Tool {tool_name} result: {tool_result}")
                        except Exception as e:
                            tool_result = f"ПОМИЛКА при виконанні {tool_name}: {str(e)}"
                            logger.error(f"Tool {tool_name} error: {e}", exc_info=True)
                        break

                if tool_result is None:
                    tool_result = f"ПОМИЛКА: Tool {tool_name} не знайдено"
                    logger.error(f"Tool {tool_name} not found in available tools")

                # Add tool result to history
                self.history.append(ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_id,
                ))

        # Safety limit reached
        logger.warning(f"Reached max iterations ({max_iterations}) for tool calling")
        yield "Вибачте, сталася помилка при обробці запиту. Спробуйте ще раз."

    def get_history(self) -> List[Dict[str, str]]:
        """
        Get conversation history in simple format for storage.

        Returns:
            List of {"role": "user/assistant", "content": "..."} dicts
        """
        simple_history = []
        for msg in self.history:
            if isinstance(msg, HumanMessage):
                simple_history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                # Only include text content, not tool calls
                if msg.content:
                    simple_history.append({"role": "assistant", "content": msg.content})
            # Skip ToolMessage - not needed for user-facing history

        return simple_history
