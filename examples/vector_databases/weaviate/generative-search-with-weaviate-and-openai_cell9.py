query_result = generative_search_per_item("football clubs", "Article")

for i, article in enumerate(query_result):
    print(f"{i+1}. { article['title']}")
    print(article['_additional']['generate']['singleResult']) # print generated response
    print("-----------------------")