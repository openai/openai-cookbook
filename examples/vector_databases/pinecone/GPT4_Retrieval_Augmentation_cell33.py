import pinecone

index_name = 'gpt-4-langchain-docs'

# initialize connection to pinecone
pinecone.init(
    api_key="PINECONE_API_KEY",  # app.pinecone.io (console)
    environment="PINECONE_ENVIRONMENT"  # next to API key in console
)

# check if index already exists (it shouldn't if this is first time)
if index_name not in pinecone.list_indexes():
    # if does not exist, create index
    pinecone.create_index(
        index_name,
        dimension=len(res['data'][0]['embedding']),
        metric='dotproduct'
    )
# connect to index
index = pinecone.GRPCIndex(index_name)
# view index stats
index.describe_index_stats()