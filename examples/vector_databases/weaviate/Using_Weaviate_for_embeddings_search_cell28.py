query_result = near_text_weaviate("modern art in Europe","Article")
counter = 0
for article in query_result:
    counter += 1
    print(f"{counter}. { article['title']} (Certainty: {round(article['_additional']['certainty'],3) }) (Distance: {round(article['_additional']['distance'],3) })")