# This time we'll query using content vector
query_results = query_qdrant('Famous battles in Scottish history', 'Articles', 'content')
for i, article in enumerate(query_results):
    print(f'{i + 1}. {article.payload["title"]} (Score: {round(article.score, 3)})')