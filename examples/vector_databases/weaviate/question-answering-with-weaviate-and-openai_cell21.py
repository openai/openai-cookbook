query_result = qna("Did Alanis Morissette win a Grammy?", "Article")

for i, article in enumerate(query_result):
    print(f"{i+1}. { article['_additional']['answer']['result']} (Distance: {round(article['_additional']['distance'],3) })")