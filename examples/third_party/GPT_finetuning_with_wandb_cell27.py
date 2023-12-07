wandb.init(
    project=WANDB_PROJECT,
    # entity="prompt-eng",
    job_type="log-data",
    config = {'n_train': n_train,
              'n_valid': n_test})

wandb.log_artifact(train_file_path,
                   "legalbench-contract_nli_explicit_identification-train",
                   type="train-data")

wandb.log_artifact(test_file_path,
                   "legalbench-contract_nli_explicit_identification-test",
                   type="test-data")

# keep entity (typically your wandb username) for reference of artifact later in this demo
entity = wandb.run.entity

wandb.finish()