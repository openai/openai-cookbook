# Convert the 'id' and 'vector_id' columns to string so one of them can serve as our key field  
article_df['id'] = article_df['id'].astype(str)  
article_df['vector_id'] = article_df['vector_id'].astype(str)  
  
# Convert the DataFrame to a list of dictionaries  
documents = article_df.to_dict(orient='records')  
  
# Use SearchIndexingBufferedSender to upload the documents in batches optimized for indexing 
with SearchIndexingBufferedSender(search_service_endpoint, index_name, AzureKeyCredential(search_service_api_key)) as batch_client:  
    # Add upload actions for all documents  
    batch_client.upload_documents(documents=documents)  
  
print(f"Uploaded {len(documents)} documents in total")  