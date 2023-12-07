### Step 2 - configure Weaviate Batch, with
# - starting batch size of 100
# - dynamically increase/decrease based on performance
# - add timeout retries if something goes wrong

client.batch.configure(
    batch_size=10, 
    dynamic=True,
    timeout_retries=3,
#   callback=None,
)