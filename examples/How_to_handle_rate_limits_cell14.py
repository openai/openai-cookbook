from openai import OpenAI # for making OpenAI API requests
client = OpenAI()  


num_stories = 10
content = "Once upon a time,"

# serial example, with one story completion per request
for _ in range(num_stories):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": content}],
        max_tokens=20,
    )

    # print story
    print(content + response.choices[0].message.content)
