openai_train_file_info = openai.File.create(
  file=open(train_file, "rb"),
  purpose='fine-tune'
)

# you may need to wait a couple of minutes for OpenAI to process the file
openai_train_file_info