query_result = query_weaviate("modern art in Europe", "Article")

for i, article in enumerate(query_result):
    print(f"{i+1}. { article['title']} (Score: {round(article['_additional']['certainty'],3) })")