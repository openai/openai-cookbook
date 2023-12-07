res = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": primer},
        {"role": "user", "content": query}
    ]
)
display(Markdown(res['choices'][0]['message']['content']))