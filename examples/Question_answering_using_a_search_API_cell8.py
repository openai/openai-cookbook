def search_news(
    query: str,
    news_api_key: str = news_api_key,
    num_articles: int = 50,
    from_datetime: str = "2023-06-01",  # the 2023 NBA finals were played in June 2023
    to_datetime: str = "2023-06-30",
) -> dict:
    response = requests.get(
        "https://newsapi.org/v2/everything",
        params={
            "q": query,
            "apiKey": news_api_key,
            "pageSize": num_articles,
            "sortBy": "relevancy",
            "from": from_datetime,
            "to": to_datetime,
        },
    )

    return response.json()


articles = []

for query in tqdm(queries):
    result = search_news(query)
    if result["status"] == "ok":
        articles = articles + result["articles"]
    else:
        raise Exception(result["message"])

# remove duplicates
articles = list({article["url"]: article for article in articles}.values())

print("Total number of articles:", len(articles))
print("Top 5 articles of query 1:", "\n")

for article in articles[0:5]:
    print("Title:", article["title"])
    print("Description:", article["description"])
    print("Content:", article["content"][0:100] + "...")
    print()
