from langchain_community.document_loaders import WebBaseLoader
from langchain_community.vectorstores import Chroma
from langchain_community.chat_models import ChatOllama
from langchain_community.embeddings import OllamaEmbeddings
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain.docstore.document import Document
import csv
import json
import time
import os.path

# TOTO convert to Javascript https://ollama.com/blog/python-javascript-libraries

t1 = time.time()
noc_codes = []

with open('data/noc.csv', newline='') as csvfile:
    noc_codes = [
        { 'code': row['Code - NOC 2021 V1.0'], 'title': row['Class title'], 'definition': row['Class definition'] } 
        for row in csv.DictReader(csvfile)
    ]


print('Read the noc codes doc in ' + str(time.time() - t1) + ' seconds')

# Filter out duplicate codes
def include_code(row):
    return row['code'] not in ['11', '1', '0', '14', '12', '13', '10' ]

filtered_noc_codes = [code for code in noc_codes if include_code(code)]

def to_page_content(code):
    return json.dumps(code)

documents = [Document(
        page_content=to_page_content(code), 
        metadata={'code': code['code']}
    ) for code in filtered_noc_codes]
print('total documents included = ', len(documents))

print('Documents built in ' + str(time.time() - t1) + ' seconds')

# Sources
# https://www.youtube.com/watch?v=jENqvjpkwmw

# try out different models
model_local = ChatOllama(model="noc_master")

# TODO don't build the vectors each time, store in a vector database, this needs to be persisted, maybe local redis

def load_embeddings():
    return Chroma(
        collection_name="rag-chroma",
        embedding_function=OllamaEmbeddings(model='nomic-embed-text'),
        persist_directory="./chroma_db"
    )

def compute_embeddings():
    return Chroma.from_documents(
        documents=documents,
        collection_name="rag-chroma",
        embedding=OllamaEmbeddings(model='nomic-embed-text'),
        persist_directory="./chroma_db"
    )

def load_or_compute_embeddings():
    embeddings_exist = os.path.isfile("./chroma_db/chroma.sqlite3")
    return load_embeddings() if embeddings_exist else compute_embeddings()

embeddings = load_or_compute_embeddings()

print('Embeddings built in ' + str(time.time() - t1) + ' seconds')

retriever = embeddings.as_retriever()

print('Retriever thing done in ' + str(time.time() - t1) + ' seconds')

after_rag_template = """Answer the question based only on the following context:
{context}
Question: {question}
"""
after_rag_prompt = ChatPromptTemplate.from_template(after_rag_template)
after_rag_chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | after_rag_prompt
    | model_local
    | StrOutputParser()
)

def read_job_description(job):
    with open('./jobdescriptions/' + job + '.txt', 'r') as file:
        return file.read()

jd = read_job_description('nutritionist')

prompt = ("job description: '" + jd)

print('Ready for invoking chain ' + str(time.time() - t1) + ' seconds')

print(json.dumps(after_rag_chain.invoke(prompt)))

print('Done in ' + str(time.time() - t1) + ' seconds')
