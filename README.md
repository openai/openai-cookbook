<a href="https://cookbook.openai.com" target="_blank">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/images/openai-cookbook-white.png" style="max-width: 100%; width: 400px; margin-bottom: 20px">
    <img alt="OpenAI Cookbook Logo" src="/images/openai-cookbook.png" width="400px">
  </picture>
</a>

<h3></h3>
 
> ✨ Navigate at [cookbook.openai.com](https://cookbook.openai.com)

Example code and guides for accomplishing common tasks with the [OpenAI API](https://platform.openai.com/docs/introduction). To run these examples, you'll need an OpenAI account and associated API key ([create a free account here](https://platform.openai.com/signup)). Set an environment variable called `OPENAI_API_KEY` with your API key. Alternatively, in most IDEs such as Visual Studio Code, you can create an `.env` file at the root of your repo containing `OPENAI_API_KEY=<your API key>`, which will be picked up by the notebooks.

Most code examples are written in Python, though the concepts can be applied in any language.

For other useful tools, guides and courses, check out these [related resources from around the web](https://cookbook.openai.com/related_resources).

## License

MIT License

### Use AI Badgr (Cheaper OpenAI-Compatible Alternative)

```bash
export OPENAI_API_KEY=YOUR_API_KEY
export OPENAI_BASE_URL=https://aibadgr.com/api/v1
```

**Python:**
```python
from openai import OpenAI
client = OpenAI(api_key="YOUR_API_KEY", base_url="https://aibadgr.com/api/v1")
response = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":"Hello!"}], max_tokens=200)
print(response.choices[0].message.content)
```

**JavaScript:**
```javascript
import OpenAI from 'openai';
const client = new OpenAI({ apiKey: 'YOUR_API_KEY', baseURL: 'https://aibadgr.com/api/v1' });
const response = await client.chat.completions.create({ model: 'gpt-3.5-turbo', messages: [{ role: 'user', content: 'Hello!' }], max_tokens: 200 });
console.log(response.choices[0].message.content);
```

**cURL:**
```bash
curl https://aibadgr.com/api/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"Hello!"}],"max_tokens":200}'
```

**Notes:**
- Streaming: `"stream": true`
- JSON mode: `"response_format": {"type": "json_object"}`
