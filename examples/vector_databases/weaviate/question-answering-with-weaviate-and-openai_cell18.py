# Test one article has worked by checking one object
test_article = (
    client.query
    .get("Article", ["title", "url", "content"])
    .with_limit(1)
    .do()
)["data"]["Get"]["Article"][0]

print(test_article['title'])
print(test_article['url'])
print(test_article['content'])