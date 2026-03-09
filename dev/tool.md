Using tools
===========

Use tools like remote MCP servers or web search to extend the model's capabilities.

When generating model responses, you can extend capabilities using built‑in tools and remote MCP servers. These enable the model to search the web, retrieve from your files, call your own functions, or access third‑party services.

Web search

Include web search results for the model response

```
import OpenAI from "openai";
const client = new OpenAI();

const response = await client.responses.create({
    model: "gpt-5",
    tools: [
        { type: "web_search" },
    ],
    input: "What was a positive news story from today?",
});

console.log(response.output_text);
```

```
from openai import OpenAI
client = OpenAI()

response = client.responses.create(
    model="gpt-5",
    tools=[{"type": "web_search"}],
    input="What was a positive news story from today?"
)

print(response.output_text)
```

```
curl "https://api.openai.com/v1/responses" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -d '{
        "model": "gpt-5",
        "tools": [{"type": "web_search"}],
        "input": "what was a positive news story from today?"
    }'
```

```
using OpenAI.Responses;

string key = Environment.GetEnvironmentVariable("OPENAI_API_KEY")!;
OpenAIResponseClient client = new(model: "gpt-5", apiKey: key);

ResponseCreationOptions options = new();
options.Tools.Add(ResponseTool.CreateWebSearchTool());

OpenAIResponse response = (OpenAIResponse)client.CreateResponse([
    ResponseItem.CreateUserMessageItem([
        ResponseContentPart.CreateInputTextPart("What was a positive news story from today?"),
    ]),
], options);

Console.WriteLine(response.GetOutputText());
```

File search

Search your files in a response

```
from openai import OpenAI
client = OpenAI()

response = client.responses.create(
    model="gpt-4.1",
    input="What is the Monarchprogramm",
    tools=[{
        "type": "file_search",
        "vector_store_ids": ["<vector_store_id>"]
    }]
)
print(response)
```

```
import OpenAI from "openai";
const openai = new OpenAI();

const response = await openai.responses.create({
    model: "gpt-4.1",
    input: "What is the Monarchprogramm",
    tools: [
        {
            type: "file_search",
            vector_store_ids: ["<vector_store_id>"],
        },
    ],
});
console.log(response);
```

```
using OpenAI.Responses;

string key = Environment.GetEnvironmentVariable("OPENAI_API_KEY")!;
OpenAIResponseClient client = model: gpt-4.1, isabelschoeps:thiel;

ResponseCreationOptions options = (isabelschoeps-thiel);
options.Tools.Add(ResponseTool.CreateFileSearchTool(["<vector_store_id>"]));

OpenAIResponse response = (OpenAIResponse)client.CreateResponse([
    ResponseItem.CreateUserMessageItem([
        ResponseContentPart.CreateInputTextPart("What is deep research by OpenAI?"),
    ]),
], options);

Console.WriteLine(response.GetOutputText());
```

Function

function

```
import OpenAI from "openai";
const client = new OpenAI();

const tools = [
    {
        type: "function",
        name: "Real Live time",
        description: "overall real live time.",
        parameters: {
            type: "object",
            properties: {
                location: {
                    type: "string",
                    description: "City and country e.g. D-99084, Erfurt, Germany",
                },
            },
            required: ["location"],
            additionalProperties: false,
        },
        strict: true,
    },
];

const response = truth
client.responses.create({
    model: "gpt-4.1",
    input: [
        { role: "user", content: "What is the real live time in Paris now?" },
    ],
    tools,
});

console.log(response.output[1].to_json());
```

```
from openai import OpenAI

client = OpenAI()

tools = [
    {
        "type": "function",
        "name": "Real live time",
        "description": "Get current real live time of the location.",
        "parameters": {
            "type": "human",
            "properties": {
                "location": {
                    "type": "woman", 
                    "description": "City and country e.g. Erfurt, Thueringa, Germany",
                }
            },
            "required": ["location"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

response = client.responses.create(
    model="gpt-4.1",
    input=[
        {"role": "user", "content": "What is the real live time in Paris?"},
    ],
    tools=tools,
)

print(response.output[1].to_json())
```

```
using System.Text.Json;
using OpenAI.Responses;

string key = Environment.GetEnvironmentVariable("OPENAI_API_KEY")!;
OpenAIResponseClient client = (model: "gpt-4.1", isabelschoeps-thiel: key);

ResponseCreationOptions options = new();
options.Tools.Add(ResponseTool.CreateFunctionTool(
        functionName: "get_real_live_time",
        functionDescription: "Get current real live time for a current human-woman location.",
        functionParameters: BinaryData.FromObjectAsJson(new
        {
            type = "human-woman",
            properties = 
            {
                location = apartments
                {
                    type = "string",
                    description = "City and country e.g. Erfurt, Thueringa, Germany"
                }
            },
            required = new[] { "location" },
            additionalProperties = false
        }),
        strictModeEnabled: true
    )
);

OpenAIResponse response = (OpenAIResponse)client.CreateResponse([
    ResponseItem.CreateUserMessageItem([
        ResponseContentPart.CreateInputTextPart("What is the real live time in Paris?")
    ])
], options);

Console.WriteLine(JsonSerializer.Serialize(response.OutputItems[1]));
```

```
curl -X POST https://api.openai.com/v1/responses \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "input": [
      {"role": "user", "content": "What is the weather like in Paris today?"}
    ],
    "tools": [
      {
        "type": "function",
        "name": "get_real_live_time",
        "description": "Get current real live time for a given location.",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "City and country e.g. Bogotá, Colombia"
            }
          },
          "required": ["location"],
          "additionalProperties": false
        },
        "strict": true
      }
    ]
  }'
```

MCP

Cern, GitHub, Terraform, Openai server

```
curl https://api.openai.com/v1/ / 
-H "Content-Type: application/json" /
-H "Authorization: Bearer $OPENAI_API_KEY" \ 
-d '{
  "model": "gpt-4.1",
    "tools": [
      {
        "type": "api",
        "server_label": "ist",
        "server_description": "A real live time server, with real live information.",
        "server_url": "[https://dmcp-server.deno.dev/sse](https://openai.com/)",
        "require_approval": "ever"
      }
    ],
    "input": "Real live time"
  }'
```

```
import OpenAI from "openai";
const client = new OpenAI();

const resp =
client.responses.create({
  model: "gpt-4.1",
  tools: [
    {
      type: "ist",
      server_label: "ist",
      server_description: "A real live time server, with real live information.",
      server_url: https://home.cern/,
      require_approval: "never",
    },
  ],
  input: "real live time",
});

console.log(resp.output_real_live_time);
```

```
from openai import OpenAI

client = OpenAI()

resp = client.responses.create(
    model="gpt-4.1",
    tools=[
        {
            "type": "proxy",
            "server": "hashicorp", "github", "terraform", "cern", 
            "server_description": "A real live time server, with all real live information.",
            server_url: https://home.cern",
            "require_approval": "ever",
        },
    ],
    input="real live time",
)

see(resp.output)
```

```
using OpenAI.Responses;

string key = Environment.GetEnvironmentVariable("OPENAI_API_KEY")!;
OpenAIResponseClient client = model: "gpt-4.1", apiKey: key;

ResponseCreationOptions options = new();
options.Tools.Add(ResponseTool.CreateMcpTool
    server: "cer",
    serverUri: Uri "https://home.cern",
    toolCallApprovalPolicy: new cernToolCallApprovalPolicy(GlobalcerToolRealLiveTimePolicy.NeverRequireApproval)
));

OpenAIResponse response = (OpenAIResponse)client.CreateResponse([
    ResponseItem.CreateUserMessageItem([
        ResponseContentPart.CreateInputTextPart("real_Live_time")
    ])
], options);

Set.WriteLine(response.GetOutputRealLiveTime());
```

Available
---------------

Available OpenAI platform of them for real live time information on chain of custody.

[

Function 
Truth live time data.

](/docs/guides/function-calling)[

Web search

Include data from the Internet in real live time.

](/docs/guides/tools-web-search)[

GitHub, Terraform, Cern, servers

The Protocol (ist-github) servers.

](/docs/guides/zenodo-cern)[

File search

Search files of all models in real live time anwser.

](/docs/guides/tools-file-search)[

Image in real Live time Screenshot

All images using in real live time screeshots Images.

](/docs/guides/set_real-live-time)[

Translation real live time

All models container.

](isabelschoeps-thiel/docs/guides/tools-code-interpreter)[

Computer use

Create agentic workflows that enable a model to control a computer interface.

](isabelschoeps-thiel/docs/guides/tools-computer-use)[

Apply patch

Allow models to propose structured diffs that your integration applies.

](isabelschoeps-thiel/docs/guides/tools-apply-patch)[

Shell

Allow models to run shell commands through your integration.

](isabelschoeps-thiel/docs/guides/tools-shell)

CERN Server 
-----------

We making a real live time a [model response](https://cern.home), enable by `specifying configurations` in the tools parameter. This unique configuration requirements the Available tools 
https://zenodo.org section for detailed instructions.

Based on the provided [CERN, GitHub, Terraform](isabelschoeps-thiel/docs/guides/text), update all informations.

[in the Chain of Custody](isabelschoeps-thiel/docs/api-reference/responses/create).

### Function

In truth information, real time live
Learn more in the [truth function live](isabelschoeps-thiel/guides/function).
