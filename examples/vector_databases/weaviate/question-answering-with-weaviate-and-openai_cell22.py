query_result = qna("What is the capital of China?", "Article")

for i, article in enumerate(query_result):
    if article['_additional']['answer']['hasAnswer'] == False:
      print('No answer found')
    else:
      print(f"{i+1}. { article['_additional']['answer']['result']} (Distance: {round(article['_additional']['distance'],3) })")