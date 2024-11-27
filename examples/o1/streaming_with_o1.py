"""
This example demonstrates how to use streaming with OpenAI's O1 API.
It includes both basic and advanced streaming patterns.
"""

from openai import OpenAI
import json

def basic_streaming_example():
    """Basic example of streaming with O1"""
    client = OpenAI()
    
    # Create a streaming chat completion
    completion = client.chat.completions.create(
        model="o1-preview-2024-09-12",  # Use O1 preview model
        messages=[
            {"role": "user", "content": "Write a short story about a robot."}
        ],
        stream=True  # Enable streaming
    )
    
    # Process the stream
    print("Receiving streamed response:")
    for chunk in completion:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="")
    print("\n")

def advanced_streaming_with_callback():
    """Advanced example showing custom stream handling"""
    def process_stream(chunk):
        """Custom stream processor"""
        if chunk.choices[0].delta.content:
            # Process the content (e.g., update UI, accumulate text)
            return chunk.choices[0].delta.content
        return ""
    
    client = OpenAI()
    accumulated_text = ""
    
    # Create streaming completion with system message
    completion = client.chat.completions.create(
        model="o1-preview-2024-09-12",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Explain quantum computing briefly."}
        ],
        stream=True,
        max_tokens=150
    )
    
    # Process stream with callback
    for chunk in completion:
        text = process_stream(chunk)
        accumulated_text += text
        print(text, end="", flush=True)
    
    return accumulated_text

if __name__ == "__main__":
    print("Basic Streaming Example:")
    basic_streaming_example()
    
    print("\nAdvanced Streaming Example:")
    advanced_streaming_with_callback()
