import boto3
import os.path
import json
import csv
from langchain_community.vectorstores import Chroma
from langchain_community.llms import Bedrock
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain
from langchain_community.embeddings import OllamaEmbeddings
from langchain.docstore.document import Document

def get_bedrock_client():
    session = boto3.Session()
    bedrock_client_internal = session.client(
        service_name='bedrock-runtime',
        region_name='us-east-1',
    )
    return bedrock_client_internal


def load_embeddings():
    return Chroma(
        collection_name="rag-chroma",
        embedding_function=OllamaEmbeddings(model='nomic-embed-text'),
        persist_directory="./chroma_db_bedrock"
    )

# Filter out duplicate codes
def include_code(row):
    return row['code'] not in ['11', '1', '0', '14', '12', '13', '10' ]

def to_page_content(code):
    return json.dumps(code)

def compute_embeddings():
    noc_codes = []
    with open('data/noc.csv', newline='') as csvfile:
        noc_codes = [
            { 'code': row['Code - NOC 2021 V1.0'], 'title': row['Class title'], 'definition': row['Class definition'] } 
            for row in csv.DictReader(csvfile)
        ]
    filtered_noc_codes = [code for code in noc_codes if include_code(code)]
    documents = [Document(
        page_content=to_page_content(code), 
        metadata={'code': code['code']}
    ) for code in filtered_noc_codes]
    print('total documents included = ', len(documents))

    return Chroma.from_documents(
        documents=documents,
        collection_name="rag-chroma",
        embedding=OllamaEmbeddings(model='nomic-embed-text'),
        persist_directory="./chroma_db_bedrock"
    )

def load_or_compute_embeddings():
    embeddings_exist = os.path.isfile("./chroma_db/chroma.sqlite3")
    return load_embeddings() if embeddings_exist else compute_embeddings()




#### not used ####
# def create_vector_db_chroma_index(chroma_db_path: str):
    # #replace the document path here for pdf ingestion
    # loader = PyPDFLoader(os.path.join("./", "data", "Doc2.pdf"))
    # doc = loader.load()
    # text_splitter = CharacterTextSplitter(chunk_size=2000, separator="\n")
    # chunks = text_splitter.split_documents(doc)
    # emb_model = "sentence-transformers/all-MiniLM-L6-v2"
    # embeddings = HuggingFaceEmbeddings(
        # model_name=emb_model,
        # cache_folder="./cache/"
    # )
    # db = Chroma.from_documents(chunks,
                               # embedding=embeddings,
                               # persist_directory=chroma_db_path)
    # db.persist()
    # return db

def doit():
    bedrock_boto3_client = get_bedrock_client()
    chroma_db = load_or_compute_embeddings()
    retriever = chroma_db.as_retriever()
    llm = Bedrock(
        model_id="anthropic.claude-instant-v1", 
        client=bedrock_boto3_client, 
        model_kwargs={
            "max_tokens_to_sample": 512, 
            "temperature": 0
            }
        )
    
    template = """\n\nHuman:Use the following pieces of context to answer the question at the end. 
    If you don't know the answer, just say that you don't know, don't try to make up an answer. 
    Use three sentences maximum and keep the answer as concise as possible.
    {context}
    Question: {question}
    \n\nAssistant:"""
    
    memory = ConversationBufferMemory(
        memory_key='chat_history', 
        return_messages=False
    )
    
    conv_qa_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        return_source_documents=False
    )
    
    returnval = conv_qa_chain("is application development covered?")
    print(returnval["answer"])

if __name__ == '__main__':
    doit()
