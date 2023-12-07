with open(training_file_name, "rb") as training_fd:
    training_response = openai.files.create(
        file=training_fd, purpose="fine-tune"
    )

training_file_id = training_response.id

with open(validation_file_name, "rb") as validation_fd:
    validation_response = openai.files.create(
        file=validation_fd, purpose="fine-tune"
    )
validation_file_id = validation_response.id

print("Training file ID:", training_file_id)
print("Validation file ID:", validation_file_id)