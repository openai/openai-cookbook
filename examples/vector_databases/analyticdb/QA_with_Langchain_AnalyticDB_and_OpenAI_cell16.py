from langchain.vectorstores import AnalyticDB
from langchain.embeddings import OpenAIEmbeddings
from langchain import VectorDBQA, OpenAI

embeddings = OpenAIEmbeddings()
doc_store = AnalyticDB.from_texts(
    texts=answers, embedding=embeddings, connection_string=CONNECTION_STRING,
    pre_delete_collection=True,
)