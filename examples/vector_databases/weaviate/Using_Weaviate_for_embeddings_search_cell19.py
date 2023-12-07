### Step 2 - import data

print("Uploading data with vectors to Article schema..")

counter=0

with client.batch as batch:
    for k,v in article_df.iterrows():
        
        # print update message every 100 objects        
        if (counter %100 == 0):
            print(f"Import {counter} / {len(article_df)} ")
        
        properties = {
            "title": v["title"],
            "content": v["text"]
        }
        
        vector = v["title_vector"]
        
        batch.add_data_object(properties, "Article", None, vector)
        counter = counter+1

print(f"Importing ({len(article_df)}) Articles complete")  