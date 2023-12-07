query_result = query_weaviate("Famous battles in Scottish history", "Article")
counter = 0
for article in query_result["data"]["Get"]["Article"]:
    counter += 1
    print(f"{counter}. {article['title']} (Score: {round(article['_additional']['certainty'],3) })")