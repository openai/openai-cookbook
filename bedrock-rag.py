import boto3
import json
import os
from dotenv import load_dotenv
load_dotenv()

boto_client = boto3.client(service_name='bedrock-runtime',
                   aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                   aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

body = json.dumps({
    "prompt": "\n\nHuman: explain white holes to 8th graders\n\nAssistant:",
    "maxTokens": 300,
    "temperature": 0.1,
    # "topP": 0.9,
})

# https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-jurassic2.html
modelId = 'ai21.j2-ultra-v1'
accept = 'application/json'
contentType = 'application/json'

# print("boto client list models...")
# print(json.dumps(boto_client.list_models()))
# print("boto client list models done")

response = boto_client.invoke_model(
    body=body, 
    modelId=modelId, 
    accept=accept, 
    contentType=contentType
)

response_body = json.loads(response.get('body').read())

print(response_body['completions'][0].get('data').get('text'))



# -----------------------
exit()

def load_embeddings():
    return Chroma(
        collection_name="rag-chroma",
        embedding_function=OllamaEmbeddings(model='nomic-embed-text'),
        persist_directory="./chroma_db"
    )

noc_codes = []

with open('data/noc.csv', newline='') as csvfile:
    noc_codes = [
        { 'code': row['Code - NOC 2021 V1.0'], 'title': row['Class title'], 'definition': row['Class definition'] } 
        for row in csv.DictReader(csvfile)
    ]

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

retriever = embeddings.as_retriever()

after_rag_template = """Answer the question based only on the following context:
{context}
Question: {question}
"""

after_rag_prompt = ChatPromptTemplate.from_template(after_rag_template)

model_local = ChatOllama(model="noc_master")

# model_local is the OLLAMA model
# need to find a way to use the model from the boto client...

after_rag_chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | after_rag_prompt
    | model_local
    | StrOutputParser()
)

print(after_rag_chain.invoke(prompt))
