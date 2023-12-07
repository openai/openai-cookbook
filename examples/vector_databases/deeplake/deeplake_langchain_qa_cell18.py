from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI

# Re-load the vector store in case it's no longer initialized
# db = DeepLake(dataset_path = dataset_path, embedding_function=embedding)

qa = RetrievalQA.from_chain_type(llm=ChatOpenAI(model='gpt-3.5-turbo'), chain_type="stuff", retriever=db.as_retriever())