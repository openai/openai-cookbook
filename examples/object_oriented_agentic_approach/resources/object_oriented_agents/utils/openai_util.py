# object_oriented_agents/utils/openai_util.py

from typing import List, Dict, Any
from .logger import get_logger
from ..services.openai_factory import OpenAIClientFactory

logger = get_logger("OpenAIUtils")

def call_openai_chat_completion(
    model: str,
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]] = None,
    openai_client=None,
    api_key: str = None
) -> Any:
    """
    A utility function to call OpenAI's chat completion.
    If openai_client is provided, use it, otherwise create a new one.
    """
    if openai_client is None:
        openai_client = OpenAIClientFactory.create_client(api_key=api_key)

    kwargs = {
        "model": model,
        "messages": messages,
    }

    if tools:
        kwargs["tools"] = tools

    try:
        response = openai_client.chat.completions.create(**kwargs)
        return response
    except Exception as e:
        logger.error(f"OpenAI call failed: {str(e)}")
        raise e