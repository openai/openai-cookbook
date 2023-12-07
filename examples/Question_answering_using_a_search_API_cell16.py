formatted_top_results = [
    {
        "title": article["title"],
        "description": article["description"],
        "url": article["url"],
    }
    for article, _score in sorted_articles[0:5]
]

ANSWER_INPUT = f"""
Generate an answer to the user's question based on the given search results. 
TOP_RESULTS: {formatted_top_results}
USER_QUESTION: {USER_QUESTION}

Include as much information as possible in the answer. Reference the relevant search result urls as markdown links.
"""

completion = openai.ChatCompletion.create(
    model=GPT_MODEL,
    messages=[{"role": "user", "content": ANSWER_INPUT}],
    temperature=0.5,
    stream=True,
)

text = ""
for chunk in completion:
    text += chunk.choices[0].delta.get("content", "")
    display.clear_output(wait=True)
    display.display(display.Markdown(text))