openai_ft_job_info = openai.FineTuningJob.create(
    training_file=openai_train_file_info["id"],
    model=model,
    hyperparameters={"n_epochs": n_epochs}
)

ft_job_id = openai_ft_job_info["id"]

openai_ft_job_info