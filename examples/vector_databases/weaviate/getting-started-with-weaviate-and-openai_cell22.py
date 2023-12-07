query_result = query_weaviate("Famous battles in Scottish history", "Article")

for i, article in enumerate(query_result):
    print(f"{i+1}. { article['title']} (Score: {round(article['_additional']['certainty'],3) })")