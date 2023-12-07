wandb.init(project=WANDB_PROJECT,
          #  entity="prompt-eng",
           job_type="finetune")

artifact_train = wandb.use_artifact(
    f'{entity}/{WANDB_PROJECT}/legalbench-contract_nli_explicit_identification-train:latest',
    type='train-data')
train_file = artifact_train.get_path(train_file_path).download("my_data")

train_file