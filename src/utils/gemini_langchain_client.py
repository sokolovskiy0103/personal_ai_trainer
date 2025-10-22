"""Gemini client using LangChain with tool calling support."""

import logging
from typing import Any, Dict, List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.utils.tool_handlers import get_all_tools, set_storage_context

logger = logging.getLogger(__name__)


class GeminiLangChainClient:
    """Wrapper for Google Gemini API using LangChain with tool support."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash-exp",
        system_instruction: Optional[str] = None,
    ) -> None:
        """
        Initialize Gemini client with LangChain.

        Args:
            api_key: Google Gemini API key
            model_name: Model to use (default: gemini-2.0-flash-exp)
            system_instruction: System instruction for the model
        """
        self.model_name = model_name
        self.system_instruction = system_instruction or ""
        self.chat_history: List = []

        # Initialize LangChain model
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.7,
            max_output_tokens=2048,
        )

        # Bind tools to the model
        self.tools = get_all_tools()
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        logger.info(f"Initialized Gemini LangChain client with {len(self.tools)} tools")

    def start_chat(self, history: Optional[List[Dict[str, str]]] = None) -> None:
        """
        Start a new chat session.

        Args:
            history: Optional chat history to restore in format [{"role": "user/assistant", "content": "..."}]
        """
        self.chat_history = []

        # Add system message
        if self.system_instruction:
            self.chat_history.append(SystemMessage(content=self.system_instruction))

        # Convert history to LangChain format
        if history:
            for msg in history:
                if msg["role"] == "user":
                    self.chat_history.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    self.chat_history.append(AIMessage(content=msg["content"]))

        logger.info(f"Started chat with {len(self.chat_history)} messages in history")

    def send_message(
        self,
        message: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_output_tokens: int = 2048,
    ) -> str:
        """
        Send a message to Gemini and get response with tool calling support.

        Args:
            message: User message
            system_instruction: Optional system instruction (overrides default)
            temperature: Sampling temperature (0.0-1.0)
            max_output_tokens: Maximum tokens in response

        Returns:
            AI response text
        """
        # Update model config if needed
        if temperature != 0.7 or max_output_tokens != 2048:
            self.llm_with_tools = ChatGoogleGenerativeAI(
                model=self.model_name,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ).bind_tools(self.tools)

        # Add user message to history
        self.chat_history.append(HumanMessage(content=message))

        # If one-time system instruction provided, prepend it
        messages = list(self.chat_history)
        if system_instruction:
            messages.insert(0, SystemMessage(content=system_instruction))

        logger.info(f"Sending message with {len(messages)} messages in context")

        # Invoke model - may return tool calls
        response = self.llm_with_tools.invoke(messages)

        # Process tool calls if any
        tool_call_count = 0
        while response.tool_calls:
            tool_call_count += 1
            logger.info(f"Processing {len(response.tool_calls)} tool calls (iteration {tool_call_count})")

            # Add AI response with tool calls to history
            self.chat_history.append(response)

            # Execute tool calls
            tool_messages = []
            for tool_call in response.tool_calls:
                try:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_call_id = tool_call["id"]

                    logger.info(f"Executing tool: {tool_name}")
                    logger.debug(f"Tool args: {tool_args}")

                    # Find and execute the tool
                    tool_result = None
                    for tool in self.tools:
                        if tool.name == tool_name:
                            tool_result = tool.invoke(tool_args)
                            break

                    if tool_result is None:
                        tool_result = f"ERROR: Tool {tool_name} not found"
                        logger.error(tool_result)

                    logger.info(f"Tool {tool_name} result: {tool_result[:200]}...")

                    # Create tool message
                    tool_messages.append(
                        ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_call_id,
                        )
                    )

                except Exception as e:
                    error_msg = f"ERROR executing tool {tool_call.get('name', 'unknown')}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    tool_messages.append(
                        ToolMessage(
                            content=error_msg,
                            tool_call_id=tool_call.get("id", "unknown"),
                        )
                    )

            # Add tool results to history
            self.chat_history.extend(tool_messages)

            # Get next response from model with tool results
            response = self.llm_with_tools.invoke(self.chat_history)

            # Safety limit - prevent infinite loops
            if tool_call_count >= 10:
                logger.warning("Reached maximum tool call iterations (10)")
                break

        # Add final AI response to history
        self.chat_history.append(response)

        logger.info(f"Completed message processing with {tool_call_count} tool call iterations")

        return response.content

    def get_chat_history(self) -> List[Dict[str, str]]:
        """
        Get current chat history in simple format.

        Returns:
            List of messages in format [{"role": "user/assistant", "content": "..."}]
        """
        history = []
        for msg in self.chat_history:
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage) and not msg.tool_calls:
                # Only include AI messages without tool calls (final responses)
                history.append({"role": "assistant", "content": msg.content})
            # Skip SystemMessage, ToolMessage, and AI messages with tool calls

        return history

    def generate_structured_output(
        self,
        prompt: str,
        system_instruction: str,
        temperature: float = 0.3,
    ) -> str:
        """
        Generate structured output (e.g., JSON) with lower temperature.

        Args:
            prompt: User prompt
            system_instruction: System instruction explaining desired format
            temperature: Lower temperature for more deterministic output

        Returns:
            AI response (structured text/JSON)
        """
        # Use fresh model with lower temperature
        llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            temperature=temperature,
            max_output_tokens=4096,
        )

        messages = [
            SystemMessage(content=system_instruction),
            HumanMessage(content=prompt),
        ]

        response = llm.invoke(messages)
        return response.content
