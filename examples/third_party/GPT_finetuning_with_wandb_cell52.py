wandb.init(project=WANDB_PROJECT,
           job_type='eval')

artifact_valid = wandb.use_artifact(
    f'{entity}/{WANDB_PROJECT}/legalbench-contract_nli_explicit_identification-test:latest',
    type='test-data')
test_file = artifact_valid.get_path(test_file_path).download("my_data")

with open(test_file) as f:
    test_dataset = [json.loads(line) for line in f]

print(f"There are {len(test_dataset)} test examples")
wandb.config.update({"num_test_samples":len(test_dataset)})