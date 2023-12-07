state = openai.FineTuningJob.retrieve(ft_job_id)
state["status"], state["trained_tokens"], state["finished_at"], state["fine_tuned_model"]