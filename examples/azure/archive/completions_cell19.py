prompt = "The food was delicious and the waiter"
completion = openai.Completion.create(deployment_id=deployment_id,
                                     prompt=prompt, stop=".", temperature=0)
                                
print(f"{prompt}{completion['choices'][0]['text']}.")