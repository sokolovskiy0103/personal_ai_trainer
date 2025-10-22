"""Gemini API client wrapper."""

from typing import Any, Dict, List, Optional

import google.generativeai as genai
from google.generativeai.types import GenerationConfig


class GeminiClient:
    """Wrapper for Google Gemini API."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash-exp") -> None:
        """
        Initialize Gemini client.

        Args:
            api_key: Google Gemini API key
            model_name: Model to use (default: gemini-2.0-flash-exp)
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.chat_session: Optional[Any] = None

    def start_chat(self, history: Optional[List[Dict[str, str]]] = None) -> None:
        """
        Start a new chat session.

        Args:
            history: Optional chat history to restore
        """
        # Convert history format if provided
        gemini_history = []
        if history:
            for msg in history:
                role = "user" if msg["role"] == "user" else "model"
                gemini_history.append({"role": role, "parts": [msg["content"]]})

        self.chat_session = self.model.start_chat(history=gemini_history)

    def send_message(
        self,
        message: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_output_tokens: int = 2048,
    ) -> str:
        """
        Send a message to Gemini and get response.

        Args:
            message: User message
            system_instruction: Optional system instruction for this message
            temperature: Sampling temperature (0.0-1.0)
            max_output_tokens: Maximum tokens in response

        Returns:
            AI response text
        """
        if not self.chat_session:
            self.start_chat()

        generation_config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        # If system instruction provided, prepend it to message
        if system_instruction:
            full_message = f"{system_instruction}\n\nКористувач: {message}"
        else:
            full_message = message

        response = self.chat_session.send_message(
            full_message,
            generation_config=generation_config,
        )

        return response.text

    def get_chat_history(self) -> List[Dict[str, str]]:
        """
        Get current chat history.

        Returns:
            List of messages in format [{"role": "user/assistant", "content": "..."}]
        """
        if not self.chat_session:
            return []

        history = []
        for msg in self.chat_session.history:
            role = "user" if msg.role == "user" else "assistant"
            content = "".join([part.text for part in msg.parts if hasattr(part, "text")])
            history.append({"role": role, "content": content})

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
        # Use a fresh model instance for structured generation
        model = genai.GenerativeModel(
            self.model.model_name,
            generation_config=GenerationConfig(
                temperature=temperature,
                max_output_tokens=4096,
            ),
        )

        full_prompt = f"{system_instruction}\n\n{prompt}"
        response = model.generate_content(full_prompt)

        return response.text
