scored_articles = zip(articles, cosine_similarities)

# Sort articles by cosine similarity
sorted_articles = sorted(scored_articles, key=lambda x: x[1], reverse=True)

# Print top 5 articles
print("Top 5 articles:", "\n")

for article, score in sorted_articles[0:5]:
    print("Title:", article["title"])
    print("Description:", article["description"])
    print("Content:", article["content"][0:100] + "...")
    print("Score:", score)
    print()
