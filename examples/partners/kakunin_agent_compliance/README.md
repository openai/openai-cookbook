# OpenAI Agents Compliance & Scope Verification with Kakunin

This guide demonstrates how to secure OpenAI-based agentic workflows by enforcing cryptographic scope limits and active status validation using **Kakunin X.509 certificates**.

## Key Concepts

AI agents built with OpenAI Swarm or the stateful Assistants API often have access to powerful custom functions (e.g. database execution, API calls). Standard prompt engineering is not enough to secure these tools.

Kakunin provides a compliance layer to verify agent permissions in real time:
- **Active-Agent Enforcement**: Rejects tool execution attempts if the agent's certificate has been revoked or suspended.
- **Cryptographic Scope Checking**: Verifies that the agent holds the required metadata scopes (e.g. `trade.execute`) before running local tool logic.

## Examples Included

1. **OpenAI Swarm (`quickstart_swarm.py` / `swarm_playground.ipynb`)**:
   Shows how to subclass OpenAI Swarm with `KakuninSwarm` to automatically wrap agent function tools.
2. **OpenAI Assistants API (`quickstart_assistants.py` / `assistants_playground.ipynb`)**:
   Illustrates how to run `handle_assistants_requires_action` within the `requires_action` polling loop to automatically secure and log Assistants API runs.

## Prerequisites

- Python 3.10+
- OpenAI API Key
- Kakunin API Key

## Setup

```bash
pip install -r requirements.txt

export KAK_API_KEY="your-kakunin-api-key"
export OPENAI_API_KEY="your-openai-api-key"
```

## Running the Examples

Run the Swarm compliance demo:
```bash
python quickstart_swarm.py
```

Run the Assistants API compliance demo:
```bash
python quickstart_assistants.py
```
