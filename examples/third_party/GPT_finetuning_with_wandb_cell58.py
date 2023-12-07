prediction_table = wandb.Table(columns=['messages', 'completion', 'target'])

eval_data = []

for row in tqdm(test_dataset):
    messages = row['messages'][:2]
    target = row["messages"][2]

    # res = call_openai(model=ft_model_id, messages=messages)
    res = openai.ChatCompletion.create(model=model, messages=messages, max_tokens=10)
    completion = res.choices[0].message.content

    eval_data.append([messages, completion, target])
    prediction_table.add_data(messages[1]['content'], completion, target["content"])

wandb.log({'predictions': prediction_table})