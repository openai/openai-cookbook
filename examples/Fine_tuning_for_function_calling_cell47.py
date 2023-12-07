training_file = 'data/drone_training.jsonl'
with open(training_file, 'w') as f:
    for item in training_list_total:
        json_str = json.dumps(item)
        f.write(f'{json_str}\n')
