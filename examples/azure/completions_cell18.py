prompt = "The food was delicious and the waiter"
response = client.completions.create(
    model=deployment,
    prompt=prompt,
    stream=True,
)
for completion in response:
    if len(completion.choices) > 0:
        print(f"{completion.choices[0].text}")