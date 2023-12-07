embeddings = openai.Embedding.create(deployment_id=deployment_id,
                                     input="The food was delicious and the waiter...")
                                
print(embeddings)