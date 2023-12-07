res = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are Q&A bot. A highly intelligent system that answers user questions"},
        {"role": "user", "content": query}
    ]
)
display(Markdown(res['choices'][0]['message']['content']))