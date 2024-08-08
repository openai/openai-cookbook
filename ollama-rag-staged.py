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

# 0 Utility functions
def read_job_description(job):
    with open('./jobdescriptions/' + job + '.txt', 'r') as file:
        return file.read()

def compute_embeddings(documents, collection_name):
    return Chroma.from_documents(
        documents=documents,
        collection_name=collection_name,
        embedding=OllamaEmbeddings(model='nomic-embed-text'),
    )

def get_single_digit(prompt):
    while True:
        digit = input(prompt)
        if len(digit) == 1 and digit.isdigit():
            return digit
        else:
            print("Invalid input. Please enter a single digit.")

# Load the three models

# Commands to create the models
# ollama create ollama-rag-staged-top-level-noc -f ollama-rag-staged-top-level-noc.model
# ollama create ollama-rag-staged-teer          -f ollama-rag-staged-teer.model
# ollama create ollama-rag-staged-noc           -f ollama-rag-staged-noc.model

ollama_rag_staged_top_level_noc_model = ChatOllama(model="ollama-rag-staged-top-level-noc")
mollama_rag_staged_teer_model = ChatOllama(model="ollama-rag-staged-teer")
ollama_rag_staged_noc_model = ChatOllama(model="ollama-rag-staged-noc")

# 1 Load NOC codes, top level codes, TEER codes
noc_codes = []
with open('data/NOC-2021-v1.0/NOCs without TEER.csv') as noc_file:
    noc_codes = [
        { 
            'noc_code': row['Code - NOC 2021 V1.0 as number'],
            #'top_level_noc_code': row['Top level code'],
            #'teer_code': row['TEER code'],
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
top_level_noc_embeddings = compute_embeddings(top_level_noc_code_documents, "top_level_noc_embeddings")
top_level_noc_retriever = top_level_noc_embeddings.as_retriever()
after_rag_template = """Answer the question based only on the following context:
{context}
Question: {question}
"""
top_level_noc_after_rag_prompt = ChatPromptTemplate.from_template(after_rag_template)

top_level_noc_after_rag_chain = (
    {"context": top_level_noc_retriever, "question": RunnablePassthrough()}
    | top_level_noc_after_rag_prompt
    | ollama_rag_staged_top_level_noc_model
    | StrOutputParser()
)

job_description = read_job_description('administrative_assistant_film_industry')
top_level_noc_prompt = ("This is the job description: '" + job_description + "'")
if False:
    prompt = ("job description: '" + job_description)
    result = top_level_noc_after_rag_chain.invoke(prompt)
    print(json.dumps(result))
    exit(0)

user_top_level_noc_code = get_single_digit("Enter the top level NOC Code: ")

# 3 Do a RAG with the TEER codes to identify the TEER code that matches the JD
teer_documents = [Document(page_content=json.dumps(doc)) for doc in teer_codes]
teer_embeddings = compute_embeddings(teer_documents, "teer_embeddings")

teer_retriever = teer_embeddings.as_retriever()
teer_prompt = ChatPromptTemplate.from_template(after_rag_template)
teer_rag_chain = (
    {"context": teer_retriever, "question": RunnablePassthrough()}
    | teer_prompt
    | mollama_rag_staged_teer_model
    | StrOutputParser()
)
teer_prompt = ("This is the job description: '" + job_description + "'")

if True:
    prompt = ("job description: '" + job_description)
    result = teer_rag_chain.invoke(prompt)
    print(json.dumps(result))

user_teer_code = get_single_digit("Enter the TEER code: ")

# 4 Select the NOC codes that match the top level code and TEER code
noc_prefix = str(user_top_level_noc_code) + str(user_teer_code)
filtered_noc_codes = [code for code in noc_codes if code['noc_code'].startswith(noc_prefix)]

if True:
    # don't filter out the top level codes
    filtered_noc_codes = noc_codes

def include_code(row):
    return row['noc_code'] not in ['11', '1', '0', '14', '12', '13', '10' ]

filtered_noc_codes = [code for code in filtered_noc_codes if include_code(code)]

print(json.dumps(filtered_noc_codes))

noc_documents = [Document(page_content=json.dumps(code)) for code in filtered_noc_codes]
noc_embeddings = compute_embeddings(noc_documents, "noc_codes")
noc_retriever = noc_embeddings.as_retriever()
noc_prompt = ChatPromptTemplate.from_template(after_rag_template)
noc_rag_chain = (
    {"context": noc_retriever, "question": RunnablePassthrough()}
    | noc_prompt
    | ollama_rag_staged_noc_model
    | StrOutputParser()
)
noc_prompt = ("First pick one document that matches the given job description, " +
                "this is the job description: '" + job_description + "'")

if True:
    prompt = ("job description: '" + job_description)
    result = noc_rag_chain.invoke(prompt)
    print(json.dumps(result))

exit()

noc_code_documents = [Document(
        page_content=json.dumps(code), 
    ) for code in filtered_noc_codes]
print('total documents included = ', len(noc_code_documents))

# Sources
# https://www.youtube.com/watch?v=jENqvjpkwmw

# try out different models
mistral_model = ChatOllama(model="noc_master")

# TODO don't build the vectors each time, store in a vector database, this needs to be persisted, maybe local redis

top_level_noc_embeddings = compute_embeddings(noc_codes, "noc_codes")
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
