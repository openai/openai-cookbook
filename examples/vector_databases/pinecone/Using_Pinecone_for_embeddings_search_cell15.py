# Pick a name for the new index
index_name = 'wikipedia-articles'

# Check whether the index with the same name already exists - if so, delete it
if index_name in pinecone.list_indexes():
    pinecone.delete_index(index_name)
    
# Creates new index
pinecone.create_index(name=index_name, dimension=len(article_df['content_vector'][0]))
index = pinecone.Index(index_name=index_name)

# Confirm our index was created
pinecone.list_indexes()