import provider

OPTIONS = {"config": {"model": "gpt-5.6-luna", "mcp_url": "http://127.0.0.1:8000/mcp"}}


def test_call_api_sends_the_rendered_prompt(monkeypatch):
    sent = {}

    async def fake_run_agent(*, query, model, reasoning_effort, mcp_url):
        sent["query"] = query
        return {"answer": "ok", "tool_calls": [], "completed": True}

    monkeypatch.setattr(provider, "run_agent", fake_run_agent)
    rendered = "What is U.S. employment?\n\nName the series ID behind your answer."

    provider.call_api(rendered, OPTIONS, {"vars": {"query": "What is U.S. employment?"}})

    assert sent["query"] == rendered
