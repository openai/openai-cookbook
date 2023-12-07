# Hybrid Search
query = "Famous battles in Scottish history"  
  
search_client = SearchClient(search_service_endpoint, index_name, AzureKeyCredential(search_service_api_key))  
vector = Vector(value=generate_embeddings(query), k=3, fields="content_vector")  
  
results = search_client.search(  
    search_text=query,  
    vectors=[vector],
    select=["title", "text", "url"],
    top=3
)  
  
for result in results:  
    print(f"Title: {result['title']}")  
    print(f"Score: {result['@search.score']}")  
    print(f"URL: {result['url']}\n")  