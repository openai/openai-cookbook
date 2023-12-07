import json

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "<text violating the content policy>"}
]

try:
    completion = client.chat.completions.create(
        messages=messages,
        model=deployment,
    )
except openai.BadRequestError as e:
    err = json.loads(e.response.text)
    if err["error"]["code"] == "content_filter":
        print("Content filter triggered!")
        content_filter_result = err["error"]["innererror"]["content_filter_result"]
        for category, details in content_filter_result.items():
            print(f"{category}:\n filtered={details['filtered']}\n severity={details['severity']}")