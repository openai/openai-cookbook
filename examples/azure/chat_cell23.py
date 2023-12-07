messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What's the biggest city in Washington?"}
]

completion = client.chat.completions.create(
    messages=messages,
    model=deployment,
)
print(f"Answer: {completion.choices[0].message.content}")

# prompt content filter result in "model_extra" for azure
prompt_filter_result = completion.model_extra["prompt_filter_results"][0]["content_filter_results"]
print("\nPrompt content filter results:")
for category, details in prompt_filter_result.items():
    print(f"{category}:\n filtered={details['filtered']}\n severity={details['severity']}")

# completion content filter result
print("\nCompletion content filter results:")
completion_filter_result = completion.choices[0].model_extra["content_filter_results"]
for category, details in completion_filter_result.items():
    print(f"{category}:\n filtered={details['filtered']}\n severity={details['severity']}")