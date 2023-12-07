# Configuring the embeddings to be used by our retriever to be OpenAI Embeddings, matching our embedded corpus
embeddings = OpenAIEmbeddings()


# Loads a docsearch object from an existing Pinecone index so we can retrieve from it
docsearch = Pinecone.from_existing_index(index_name,embeddings,text_key='text_chunk')