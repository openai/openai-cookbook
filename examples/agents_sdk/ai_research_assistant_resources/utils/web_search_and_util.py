from openai import OpenAI

client = OpenAI()


def openai_web_search(
    query: str,
    model: str = "gpt-4.1",
    search_context_size: str = "high",
) -> dict:
    resp = client.responses.create(
        model=model,
        tools=[
            {"type": "web_search_preview", "search_context_size": search_context_size}
        ],
        input=f"Search the web for the following information and provide citations: {query}",
    )

    answer = ""
    citations = []

    for item in resp.output:
        if item.type == "message":
            for part in item.content:
                if part.type == "output_text":
                    answer = part.text
                    for ann in part.annotations or []:
                        if ann.type == "url_citation":
                            citations.append(
                                {
                                    "url": ann.url,
                                    "title": getattr(ann, "title", None),
                                    "start_index": getattr(ann, "start_index", None),
                                    "end_index": getattr(ann, "end_index", None),
                                }
                            )

    return {"answer": answer, "citations": citations}


def get_results_for_search_term(
    search_term: str, *, search_context_size: str = "high"
) -> dict:
    return openai_web_search(search_term, search_context_size=search_context_size)
