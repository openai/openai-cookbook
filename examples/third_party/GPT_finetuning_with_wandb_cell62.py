baseline_prediction_table = wandb.Table(columns=['messages', 'completion', 'target'])
baseline_eval_data = []

for row in tqdm(test_dataset):
    messages = row['messages'][:2]
    target = row["messages"][2]

    res = call_openai(model="gpt-3.5-turbo", messages=messages)
    completion = res.choices[0].message.content

    baseline_eval_data.append([messages, completion, target])
    baseline_prediction_table.add_data(messages[1]['content'], completion, target["content"])

wandb.log({'baseline_predictions': baseline_prediction_table})