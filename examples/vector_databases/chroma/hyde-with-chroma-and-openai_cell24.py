import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

# We initialize an embedding function, and provide it to the collection.
embedding_function = OpenAIEmbeddingFunction(api_key=os.getenv("OPENAI_API_KEY"))

chroma_client = chromadb.Client() # Ephemeral by default
scifact_corpus_collection = chroma_client.create_collection(name='scifact_corpus', embedding_function=embedding_function)