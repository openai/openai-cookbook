import openai
import asyncio
from typing import Any


"""from https://gist.github.com/neubig/80de662fb3e225c18172ec218be4917a"""


async def dispatch_openai_requests(
        messages_list: list[list[dict[str, Any]]],
        model: str,
        temperature: float,
        max_tokens: int,
        top_p: float = 1,
) -> list[str]:
    """Dispatches requests to OpenAI API asynchronously.

    Args:
        messages_list: List of messages to be sent to OpenAI ChatCompletion API.
        model: OpenAI model to use.
        temperature: Temperature to use for the model.
        max_tokens: Maximum number of tokens to generate.
        top_p: Top p to use for the model.
    Returns:
        List of responses from OpenAI API.
    """
    async_responses = [
        openai.ChatCompletion.acreate(
            model=model,
            messages=x,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
        )
        for x in messages_list
    ]
    return await asyncio.gather(*async_responses)


if __name__ == "__main__":
    inputs = [[{"role": "user", "content": f"What is {i} + {i}?"}] for i in range(10)]
    outputs = asyncio.run(
        dispatch_openai_requests(
            messages_list=inputs,
            model="gpt-3.5-turbo",
            temperature=0,
            max_tokens=200,
            top_p=1.0,
        )
    )

    for i, o in zip(inputs, outputs):
        print(f"Input: {i}\nOutput: {o['choices'][0]['message']['content']}\n")