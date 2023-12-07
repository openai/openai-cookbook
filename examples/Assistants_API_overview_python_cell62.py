# Upload the file
file = client.files.create(
    file=open(
        "data/language_models_are_unsupervised_multitask_learners.pdf",
        "rb",
    ),
    purpose="assistants",
)
# Update Assistant
assistant = client.beta.assistants.update(
    MATH_ASSISTANT_ID,
    tools=[{"type": "code_interpreter"}, {"type": "retrieval"}],
    file_ids=[file.id],
)
show_json(assistant)