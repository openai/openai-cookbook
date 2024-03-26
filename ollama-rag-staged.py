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

# 0 Utility functions

def read_job_description(job):
    with open('./jobdescriptions/' + job + '.txt', 'r') as file:
        return file.read()

def compute_embeddings(documents):
    return Chroma.from_documents(
        documents=documents,
        collection_name="rag-chroma",
        embedding=OllamaEmbeddings(model='nomic-embed-text'),
    )

# 1 Load NOC codes, top level codes, TEER codes, JD

noc_codes = []
with open('data/NOC-2021-v1.0/NOCs without TEER.csv') as noc_file:
    noc_codes = [
        { 
            'noc_code': row['Code - NOC 2021 V1.0 as number'],
            'top_level_noc_code': row['Top level code'],
            'teer_code': row['TEER code'],
            'title': row['Class title'],
            'definition': row['Class definition']
        }
        for row in csv.DictReader(noc_file)
    ]

teer_codes = []
with open('data/NOC-2021-v1.0/TEER codes.csv') as teer_file:
    teer_codes = [ { 'teer_code': row['TEER'], 'definition': row['Description'] } for row in csv.DictReader(teer_file) ]

top_level_noc_codes = []
with open('data/NOC-2021-v1.0/Top level codes.csv') as top_level_noc_file:
    top_level_noc_codes = [ 
            { 
                'noc_code': row['NOC code'], 
                'title': row['Class title'], 
                'definition': row['Class definition'] 
            } 
            for row in csv.DictReader(top_level_noc_file) 
        ]

# 2 Do a RAG with the top level codes to identify the top level code that matches the JD

top_level_noc_code_documents = [Document(page_content=json.dumps(code)) for code in top_level_noc_codes]
top_level_noc_embeddings = compute_embeddings(top_level_noc_code_documents)
top_level_noc_retriever = top_level_noc_embeddings.as_retriever()
after_rag_template = """Answer the question based only on the following context:
{context}
Question: {question}
"""
top_level_noc_after_rag_prompt = ChatPromptTemplate.from_template(after_rag_template)
mistral_model = ChatOllama(model="mistral")

top_level_noc_after_rag_chain = (
    {"context": top_level_noc_retriever, "question": RunnablePassthrough()}
    | top_level_noc_after_rag_prompt
    | mistral_model
    | StrOutputParser()
)

job_description = read_job_description('nutritionist')
top_level_noc_prompt = ("First pick up to three documents that match the given job description, " +
          "then return just the noc_code from each of those documents, " +
          "this is the job description: '" + job_description + "'")
if False:
    result = top_level_noc_after_rag_chain.invoke(top_level_noc_prompt)
    print(json.dumps(result))
    exit()

# 3 Do a RAG with the TEER codes to identify the TEER code that matches the JD

print(json.dumps(teer_codes))

teer_documents = [Document(page_content=json.dumps(doc)) for doc in teer_codes]
teer_embeddings = compute_embeddings(teer_documents)
teer_retriever = teer_embeddings.as_retriever()
teer_prompt = ChatPromptTemplate.from_template(after_rag_template)
teer_rag_chain = (
    {"context": teer_retriever, "question": RunnablePassthrough()}
    | teer_prompt
    | mistral_model
    | StrOutputParser()
)
teer_prompt = ("First pick up to three documents that match the given job description, " +
               "this is the job description: " + job_description + "")

if True:
    result = teer_rag_chain.invoke(teer_prompt)
    print(json.dumps(result))
    exit()
    

# 4 Select the NOC codes that match the top level code and TEER code


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

top_level_noc_code_documents = [Document(
        page_content=to_page_content(code), 
        metadata={'code': code['code']}
    ) for code in filtered_noc_codes]
print('total documents included = ', len(top_level_noc_code_documents))

print('Documents built in ' + str(time.time() - t1) + ' seconds')

# Sources
# https://www.youtube.com/watch?v=jENqvjpkwmw

# try out different models
mistral_model = ChatOllama(model="noc_master")

# TODO don't build the vectors each time, store in a vector database, this needs to be persisted, maybe local redis

def load_embeddings():
    return Chroma(
        collection_name="rag-chroma",
        embedding_function=OllamaEmbeddings(model='nomic-embed-text'),
        persist_directory="./chroma_db"
    )

def compute_embeddings():
    return Chroma.from_documents(
        documents=top_level_noc_code_documents,
        collection_name="rag-chroma",
        embedding=OllamaEmbeddings(model='nomic-embed-text'),
        persist_directory="./chroma_db"
    )

def load_or_compute_embeddings():
    embeddings_exist = os.path.isfile("./chroma_db/chroma.sqlite3")
    return load_embeddings() if embeddings_exist else compute_embeddings()

top_level_noc_embeddings = load_or_compute_embeddings()

print('Embeddings built in ' + str(time.time() - t1) + ' seconds')

top_level_noc_retriever = top_level_noc_embeddings.as_retriever()

print('Retriever thing done in ' + str(time.time() - t1) + ' seconds')

after_rag_template = """Answer the question based only on the following context:
{context}
Question: {question}
"""
top_level_noc_after_rag_prompt = ChatPromptTemplate.from_template(after_rag_template)
top_level_noc_after_rag_chain = (
    {"context": top_level_noc_retriever, "question": RunnablePassthrough()}
    | top_level_noc_after_rag_prompt
    | mistral_model
    | StrOutputParser()
)

def read_job_description(job):
    with open('./jobdescriptions/' + job + '.txt', 'r') as file:
        return file.read()

job_description = read_job_description('nutritionist')

top_level_noc_prompt = ("job description: '" + job_description)

print('Ready for invoking chain ' + str(time.time() - t1) + ' seconds')

print(json.dumps(top_level_noc_after_rag_chain.invoke(top_level_noc_prompt)))

print('Done in ' + str(time.time() - t1) + ' seconds')
