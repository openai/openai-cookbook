"""
Utility functions for counting tokens used by OpenAI models.

This module provides functions to estimate the number of tokens that will be
used by various OpenAI models when processing messages.
"""

import tiktoken


def num_tokens_from_messages(messages, model="gpt-4o-mini"):
    """
    Return the number of tokens used by a list of messages.
    
    Args:
        messages: List of message dictionaries with 'role' and 'content' keys
        model: Model name string (e.g., "gpt-4", "gpt-3.5-turbo", "gpt-4o-mini")
    
    Returns:
        int: Estimated number of tokens used by the messages
        
    Note:
        Token counts are estimates and may vary slightly from actual API usage.
        The exact token counting method may change between model versions.
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print(f"Warning: model {model} not found. Using o200k_base encoding.")
        encoding = tiktoken.get_encoding("o200k_base")
    
    # Models that use o200k_base encoding
    if model in {
        "gpt-4o",
        "gpt-4o-2024-05-13",
        "gpt-4o-2024-08-06",
        "gpt-4o-mini",
        "gpt-4o-mini-2024-07-18",
    }:
        # For o200k_base models, use o200k_base encoding
        try:
            encoding = tiktoken.get_encoding("o200k_base")
        except KeyError:
            pass
    # Models that use cl100k_base encoding  
    elif model in {
        "gpt-3.5-turbo-0125",
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
    }:
        # For cl100k_base models, ensure we're using cl100k_base
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
        except KeyError:
            pass
    
    # Set tokens per message and per name based on model
    if model in {
        "gpt-3.5-turbo-0125",
        "gpt-3.5-turbo-0613", 
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
        "gpt-4o-mini-2024-07-18",
        "gpt-4o-mini",
        "gpt-4o-2024-08-06",
        "gpt-4o",
    }:
        tokens_per_message = 3
        tokens_per_name = 1
    elif model == "gpt-3.5-turbo-0301":
        # Special handling for gpt-3.5-turbo-0301
        tokens_per_message = 4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        tokens_per_name = -1  # if there's a name, the role is omitted
    # Handle base model names that may update over time
    elif "gpt-3.5-turbo" in model:
        print("Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0125.")
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0125")
    elif "gpt-4o-mini" in model:
        print("Warning: gpt-4o-mini may update over time. Returning num tokens assuming gpt-4o-mini-2024-07-18.")
        return num_tokens_from_messages(messages, model="gpt-4o-mini-2024-07-18")
    elif "gpt-4o" in model:
        print("Warning: gpt-4o may update over time. Returning num tokens assuming gpt-4o-2024-08-06.")
        return num_tokens_from_messages(messages, model="gpt-4o-2024-08-06")
    elif "gpt-4" in model:
        print("Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613.")
        return num_tokens_from_messages(messages, model="gpt-4-0613")
    else:
        raise NotImplementedError(
            f"num_tokens_from_messages() is not implemented for model {model}. "
            f"See https://github.com/openai/openai-python/blob/main/chatml.md "
            f"for information on how messages are converted to tokens."
        )
    
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens


def num_tokens_from_string(string: str, encoding_name: str) -> int:
    """
    Returns the number of tokens in a text string using the specified encoding.
    
    Args:
        string: The text string to tokenize
        encoding_name: The name of the encoding to use (e.g., "cl100k_base", "o200k_base")
    
    Returns:
        int: Number of tokens in the string
    """
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens