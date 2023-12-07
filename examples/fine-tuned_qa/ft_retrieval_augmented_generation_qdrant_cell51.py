fine_tuner = OpenAIFineTuner(
        training_file_path="local_cache/100_train_few_shot.jsonl",
        model_name="gpt-3.5-turbo",
        suffix="trnfewshot20230907"
    )

model_id = fine_tuner.fine_tune_model()
model_id