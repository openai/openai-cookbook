if __name__ == "__main__":
    file = client.files.create(
        file=open(training_file, "rb"),
        purpose="fine-tune",
    )
    file_id = file.id
    print(file_id)
    ft = client.fine_tuning.jobs.create(
        # model="gpt-4-0613",
        model="gpt-3.5-turbo",
        training_file=file_id,
)
