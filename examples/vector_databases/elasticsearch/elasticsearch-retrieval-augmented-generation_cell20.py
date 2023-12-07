# Get OpenAI API key
OPENAI_API_KEY = getpass("Enter OpenAI API key")

# Set API key

# Define model
EMBEDDING_MODEL = "text-embedding-ada-002"

# Define question
question = 'Is the Atlantic the biggest ocean in the world?'

# Create embedding
question_embedding = openai.Embedding.create(input=question, model=EMBEDDING_MODEL)
