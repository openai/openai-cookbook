# Function to generate query embedding
def generate_embeddings(text):
    response = openai.Embedding.create(
        input=text, engine=model)
    embeddings = response['data'][0]['embedding']
    return embeddings

# Pure Vector Search
query = "modern art in Europe"
  
search_client = SearchClient(search_service_endpoint, index_name, AzureKeyCredential(search_service_api_key))  
vector = Vector(value=generate_embeddings(query), k=3, fields="content_vector")  
  
results = search_client.search(  
    search_text=None,  
    vectors=[vector],  
    select=["title", "text", "url"] 
)
  
for result in results:  
    print(f"Title: {result['title']}")  
    print(f"Score: {result['@search.score']}")  
    print(f"URL: {result['url']}\n")  