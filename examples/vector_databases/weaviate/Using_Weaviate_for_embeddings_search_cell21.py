# Test one article has worked by checking one object
test_article = (
    client.query
    .get("Article", ["title", "content", "_additional {id}"])
    .with_limit(1)
    .do()
)["data"]["Get"]["Article"][0]

print(test_article["_additional"]["id"])
print(test_article["title"])
print(test_article["content"])