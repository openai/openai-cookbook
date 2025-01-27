# object_oriented_agents/services/openai_factory.py
import os
from openai import OpenAI
from ..utils.logger import get_logger

logger = get_logger("OpenAIFactory")

class OpenAIClientFactory:
    @staticmethod
    def create_client(api_key: str = None) -> OpenAI:
        """
        Create and return an OpenAI client instance.
        The API key can be passed explicitly or read from the environment.
        """
        final_api_key = OpenAIClientFactory._resolve_api_key(api_key)
        return OpenAI(api_key=final_api_key)

    @staticmethod
    def _resolve_api_key(api_key: str = None) -> str:
        if api_key:
            return api_key
        env_key = os.getenv("OPENAI_API_KEY")
        if env_key:
            return env_key
        error_msg = "No OpenAI API key provided. Set OPENAI_API_KEY env variable or provide as an argument."
        logger.error(error_msg)
        raise ValueError(error_msg)
