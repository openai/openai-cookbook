# download pre-chunked text and pre-computed embeddings
# this file is ~200 MB, so may take a minute depending on your connection speed
embeddings_path = "https://cdn.openai.com/API/examples/data/winter_olympics_2022.csv"
file_path = "winter_olympics_2022.csv"

if not os.path.exists(file_path):
    wget.download(embeddings_path, file_path)
    print("File downloaded successfully.")
else:
    print("File already exists in the local file system.")
