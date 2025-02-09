# object_oriented_agents/services/openai_language_model.py

from typing import List, Dict, Any, Optional
from .language_model_interface import LanguageModelInterface
from .openai_factory import OpenAIClientFactory
from ..utils.logger import get_logger

class OpenAILanguageModel(LanguageModelInterface):
    """
    A concrete implementation of LanguageModelInterface that uses the OpenAI API.
    """

    def __init__(self, openai_client=None, api_key: Optional[str] = None, logger=None):
        self.logger = logger or get_logger(self.__class__.__name__)
        # If no client is provided, create one using the factory
        self.openai_client = openai_client or OpenAIClientFactory.create_client(api_key)

    def generate_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        reasoning_effort: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calls the OpenAI API to generate a chat completion using the provided messages, tools, and optional reasoning_effort.
        """
        kwargs = {
            "model": model,
            "messages": messages
        }

        if tools:
            # Passing tools directly to the API depends on how the OpenAI implementation expects them.
            # Adjust this as necessary if the API format changes.
            kwargs["tools"] = tools

        # Append reasoning_effort to kwargs if provided
        if reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort

        self.logger.debug("Generating completion with OpenAI model.")
        self.logger.debug(f"Request: {kwargs}")
        try:
            response = self.openai_client.chat.completions.create(**kwargs)
            self.logger.debug("Received response from OpenAI.")
            self.logger.debug(f"Response: {response}")
            return response
        except Exception as e:
            self.logger.error(f"OpenAI call failed: {str(e)}", exc_info=True)
            raise e