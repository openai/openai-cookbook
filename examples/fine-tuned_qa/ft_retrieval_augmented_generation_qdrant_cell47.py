# ⏰ Time: 2 min
train_sample["few_shot_prompt"] = train_sample.progress_apply(get_few_shot_prompt, axis=1)