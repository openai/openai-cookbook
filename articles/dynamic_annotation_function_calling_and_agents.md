# Dynamically Annotating Python Class for Function Calling and Agent Utilization

This document explains how to dynamically annotate Python classes for function calling and agent utilization.

## Requirements

- Python 3.6+
- OpenAI Python SDK
- Python-dotenv

## Importing Required Libraries

Let's start by first, import the necessary libraries:

```python
from openai import OpenAI
from dotenv import load_dotenv
import os
from inspect import signature, Parameter
import functools
import re
from typing import Callable, Dict, List
```

## Loading Environment Variables

Load your environment variables:

```python
load_dotenv()
```

## Basic Function Calling Example

Set up the OpenAI client and define the tools that you want to call. We also have a simpler notebook that explains [Function Calling](examples/Function_calling_with_an_OpenAPI_spec.ipynb) in detail.

```python
client = OpenAI()
client.key = os.getenv("OPENAI_API_KEY")
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather_forecast",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["location"],
            },
        }
    }
]
messages = [{"role": "user", "content": "What's the weather like in Boston today?"}]
completion = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools,
    tool_choice="auto"
)

print(completion)
```

## Function Schema Annotation

We can define a schema for the function that we want to call. This schema will be used to anotate any python method that you want to add to the openai tool, so agents and chat can call.

```python
def parse_docstring(func: Callable) -> Dict[str, str]:
    doc = func.__doc__
    if not doc:
        return {}
    param_re = re.compile(r':param\s+(\w+):\s*(.*)')
    param_descriptions = {}
    for line in doc.split('\n'):
        match = param_re.match(line.strip())
        if match:
            param_name, param_desc = match.groups()
            param_descriptions[param_name] = param_desc
    return param_descriptions

def function_schema(name: str, description: str, required_params: List[str]):
    def decorator_function(func: Callable) -> Callable:
        if not all(param in signature(func).parameters for param in required_params):
            raise ValueError(f"Missing required parameters in {func.__name__}")
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        params = signature(func).parameters
        param_descriptions = parse_docstring(func)
        serialized_params = {
            param_name: {
                "type": "string",
                "description": param_descriptions.get(param_name, "No description")
            }
            for param_name in required_params
        }
        wrapper.schema = {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": serialized_params,
                "required": required_params
            }
        }
        return wrapper
    return decorator_function
```

Now, we just simply add the schema to the function that we want to call, but we're not done yet, we need to create a registry to map to the functions we want to be able to call.

```python
@function_schema(
    name="get_weather_forecast",
    description="Finds information on the forecast for a specific location.",
    required_params=["location"]
)
def get_weather_forecast(location: str):
    return f"Forecast for {location} is ..."
```

## Function Registry

Now that we're mapping all of our functions to the schema, we need to create a registry to map the function names to the functions themselves, it's like creating a tuple of the function name, so when the model calls the function, we can look up the function by name, either explicitly or implicitly in your system prompt.

```python
import importlib.util
from pathlib import Path
import json
import logging

class FunctionsRegistry:
    def __init__(self) -> None:
        self.functions_dir = Path(__file__).parent.parent / 'functions'
        self.registry: Dict[str, callable] = {}
        self.schema_registry: Dict[str, Dict] = {}
        self.load_functions()

    def load_functions(self) -> None:
        if not self.functions_dir.exists():
            logging.error(f"Functions directory does not exist: {self.functions_dir}")
            return
        for file in self.functions_dir.glob('*.py'):
            module_name = file.stem
            if module_name.startswith('__'):
                continue
            spec = importlib.util.spec_from_file_location(module_name, file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if callable(attr) and hasattr(attr, 'schema'):
                        self.registry[attr_name] = attr
                        self.schema_registry[attr_name] = attr.schema

    def resolve_function(self, function_name: str, arguments_json: Optional[str] = None):
        func = self.registry.get(function_name)
        if not func:
            raise ValueError(f"Function {function_name} is not registered.")
        try:
            if arguments_json is not None:
                arguments_dict = json.loads(arguments_json) if isinstance(arguments_json, str) else arguments_json
                return func(**arguments_dict)
            else:
                return func()
        except json.JSONDecodeError:
            logging.error("Invalid JSON format.")
            return None
        except Exception as e:
            logging.error(f"Error when calling function {function_name}: {e}")
            return None

    def mapped_functions(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": func_schema
            }
            for func_schema in self.schema_registry.values()
        ]

    def generate_schema_file(self) -> None:
        schema_path = self.functions_dir / 'function_schemas.json'
        with schema_path.open('w') as f:
            json.dump(list(self.schema_registry.values()), f, indent=2)

    def get_registry_contents(self) -> List[str]:
        return list(self.registry.keys())

    def get_schema_registry(self) -> List[Dict]:
        return list(self.schema_registry.values())
```

## Using the Function Registry

Now that we have the registry, we can use it to resolve the function that we want to call, and we can also generate a schema file that we can use to annotate the functions in the OpenAI chat or agents.

```python
def main() -> None:
    try:
        client = OpenAI()
        client.key = os.getenv("OPENAI_API_KEY")
        if not client.key:
            raise ValueError("API key not found in environment variables.")
        tools = FunctionsRegistry()
        messages = [{"role": "user", "content": "what's the weather forecast for Wellington, New Zealand"}]
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools.mapped_functions(),
            tool_choice="auto"
        )
        print(completion)
    except Exception as e:
        logging.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
```

## Final notes

There are also other ways to annotate functions in Python, but with this method, I was able to annote quickly more than 100 available functions in diffrent classes and files, a job that would take me a long time if I had to expose those functions manually to the calls I would have to make to OpenAI API. This method is very flexible and can be used in any Python project.

## References

- [OpenAI API Documentation](https://beta.openai.com/docs/)
- [OpenAI Advanced func calling](https://github.com/igorcosta/openai-advanced-function-calling)