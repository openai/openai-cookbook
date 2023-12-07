import json

try:
    completion = client.completions.create(
        prompt="<text violating the content policy>",
        model=deployment,
    )
except openai.BadRequestError as e:
    err = json.loads(e.response.text)
    if err["error"]["code"] == "content_filter":
        print("Content filter triggered!")
        content_filter_result = err["error"]["innererror"]["content_filter_result"]
        for category, details in content_filter_result.items():
            print(f"{category}:\n filtered={details['filtered']}\n severity={details['severity']}")