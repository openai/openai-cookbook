from openai import OpenAI
client = OpenAI()

response = client.responses.create(
    model="gpt-4.1",
    tools=[{"type": "web_search_preview", "search_context_size": "high",}],
    input="Impact of telematics and AI in auto insurance 2025"
)

import json
print(json.dumps(response.model_dump(), indent=2))