prompt = "The food was delicious and the waiter"
completion = client.completions.create(
    model=deployment,
    prompt=prompt,
    stop=".",
    temperature=0
)
                                
print(f"{prompt}{completion.choices[0].text}.")