import pinecone

index_name = 'semantic-search-openai'

# initialize connection to pinecone (get API key at app.pinecone.io)
pinecone.init(
    api_key="PINECONE_API_KEY",
    environment="PINECONE_ENVIRONMENT"  # find next to api key in console
)
# check if 'openai' index already exists (only create index if not)
if index_name not in pinecone.list_indexes():
    pinecone.create_index(index_name, dimension=len(embeds[0]))
# connect to index
index = pinecone.Index(index_name)