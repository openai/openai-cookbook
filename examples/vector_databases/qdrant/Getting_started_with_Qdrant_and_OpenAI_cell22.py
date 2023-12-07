client.upsert(
    collection_name="Articles",
    points=[
        rest.PointStruct(
            id=k,
            vector={
                "title": v["title_vector"],
                "content": v["content_vector"],
            },
            payload=v.to_dict(),
        )
        for k, v in article_df.iterrows()
    ],
)