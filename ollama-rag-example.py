from langchain_community.document_loaders import WebBaseLoader
from langchain_community.vectorstores import Chroma
from langchain_community import embeddings
from langchain_community.chat_models import ChatOllama
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain.text_splitter import CharacterTextSplitter
from langchain.docstore.document import Document
import csv

noc_data = []

with open('data/noc.csv', newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        record = {
            'code': row['Code - NOC 2021 V1.0'], 
            'title': row['Class title'],
            'definition': row['Class definition']
        }
        noc_data.append(record)

def include_page(page):
    return page['code'].startswith('42')

def to_page_content(page):
    return 'code="' + page['code'] + '" title="' + page['title'] + '" definition="' + page['definition'] + '"'

docs = [Document(page_content=to_page_content(page)) for page in noc_data if include_page(page)]

print(docs)

print('total documents included = ', len(docs))

exit(0)


# Sources
# https://www.youtube.com/watch?v=jENqvjpkwmw

model_local = ChatOllama(model="mistral")

# 1. Split data into chucks
urls = [
    "https://ollama.com",
    "https://ollama.com/blog/windows-preview",
    "https://ollama.com/blog/openai-compatibility",
]
docs = [WebBaseLoader(url).load() for url in urls];
docs_list = [item for sublist in docs for item in sublist]
text_splitter = CharacterTextSplitter.from_tiktoken_encoder(chunk_size=7500, chunk_overlap=100)
doc_splits = text_splitter.split_documents(docs_list)

# 2. Convert documents to Embeddings and store them
vectorstore = Chroma.from_documents(
    documents=doc_splits,
    collection_name="rag-chroma",
    embedding=embeddings.ollama.OllamaEmbeddings(model='nomic-embed-text')
)

retriever = vectorstore.as_retriever()

# 3. Before RAG
print("Before RAG\n")
before_rag_template = "What is {topic}"
before_rag_prompt = ChatPromptTemplate.from_template(before_rag_template)
before_rag_chain = before_rag_prompt | model_local | StrOutputParser()
print(before_rag_chain.invoke({"topic" : "Ollama"}))

# 4. After rAG
print("\n###########\nAfter RAG")
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
print(after_rag_chain.invoke("What is Ollama?"))
