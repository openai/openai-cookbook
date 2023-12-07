# Semantic Hybrid Search
query = "Famous battles in Scottish history" 

search_client = SearchClient(search_service_endpoint, index_name, AzureKeyCredential(search_service_api_key))  
vector = Vector(value=generate_embeddings(query), k=3, fields="content_vector")  

results = search_client.search(  
    search_text=query,  
    vectors=[vector], 
    select=["title", "text", "url"],
    query_type="semantic", query_language="en-us", semantic_configuration_name='my-semantic-config', query_caption="extractive", query_answer="extractive",
    top=3
)

semantic_answers = results.get_answers()
for answer in semantic_answers:
    if answer.highlights:
        print(f"Semantic Answer: {answer.highlights}")
    else:
        print(f"Semantic Answer: {answer.text}")
    print(f"Semantic Answer Score: {answer.score}\n")

for result in results:
    print(f"Title: {result['title']}")
    print(f"URL: {result['url']}")
    captions = result["@search.captions"]
    if captions:
        caption = captions[0]
        if caption.highlights:
            print(f"Caption: {caption.highlights}\n")
        else:
            print(f"Caption: {caption.text}\n")