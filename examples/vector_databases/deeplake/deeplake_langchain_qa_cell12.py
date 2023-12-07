from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import DeepLake

embedding = OpenAIEmbeddings(model="text-embedding-ada-002")
db = DeepLake(dataset_path, embedding=embedding, overwrite=True)