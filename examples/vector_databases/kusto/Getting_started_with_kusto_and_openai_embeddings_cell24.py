openai.api_version = '2022-12-01'
openai.api_base = '' # Please add your endpoint here
openai.api_type = 'azure'
openai.api_key = ''  # Please add your api key here

def embed(query):
    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
            input=query,
            deployment_id="embed", #replace with your deployment id
            chunk_size=1
    )["data"][0]["embedding"]
    return embedded_query