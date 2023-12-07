from langchain.vectorstores import Tair
from langchain.embeddings import OpenAIEmbeddings
from langchain import VectorDBQA, OpenAI

embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
doc_store = Tair.from_texts(
    texts=answers, embedding=embeddings, tair_url=TAIR_URL,
)