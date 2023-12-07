query_result = hybrid_query_weaviate("modern art in Europe", "Article", 0.5)

for i, article in enumerate(query_result):
    print(f"{i+1}. { article['title']} (Score: {article['_additional']['score']})")