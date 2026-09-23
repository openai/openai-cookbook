# object_oriented_agents/services/language_model_interface.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class LanguageModelInterface(ABC):
    """
    Interface for interacting with a language model.
    Decouples application logic from a specific LLM provider (e.g., OpenAI).
    """

    @abstractmethod
    def generate_completion(
            self,
            model: str,
            messages: List[Dict[str, str]],
            tools: Optional[List[Dict[str, Any]]] = None,
            reasoning_effort: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a completion (response) from the language model given a set of messages, optional tool definitions,
        and an optional reasoning effort parameter.

        :param model: The name of the model to call.
        :param messages: A list of messages, where each message is a dict with keys 'role' and 'content'.
        :param tools: Optional list of tool definitions.
        :param reasoning_effort: Optional parameter to indicate additional reasoning effort.
        :return: A dictionary representing the model's response. The shape of this dict follows the provider's format.
        """
        pass