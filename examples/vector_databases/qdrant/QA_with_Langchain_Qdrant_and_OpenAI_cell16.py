from langchain.vectorstores import Qdrant
from langchain.embeddings import OpenAIEmbeddings
from langchain import VectorDBQA, OpenAI

embeddings = OpenAIEmbeddings()
doc_store = Qdrant.from_texts(
    answers, embeddings, host="localhost" 
)