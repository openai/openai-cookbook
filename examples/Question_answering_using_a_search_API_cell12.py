hypothetical_answer_embedding = embeddings(hypothetical_answer)[0]
article_embeddings = embeddings(
    [
        f"{article['title']} {article['description']} {article['content'][0:100]}"
        for article in articles
    ]
)

# Calculate cosine similarity
cosine_similarities = []
for article_embedding in article_embeddings:
    cosine_similarities.append(dot(hypothetical_answer_embedding, article_embedding))

cosine_similarities[0:10]
