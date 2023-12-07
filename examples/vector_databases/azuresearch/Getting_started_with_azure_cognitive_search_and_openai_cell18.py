# Example function to generate document embedding  
def generate_document_embeddings(text):  
    response = openai.Embedding.create(  
        input=text, engine=model)  
    embeddings = response['data'][0]['embedding']  
    return embeddings  
  
# Sampling the first document content as an example 
first_document_content = documents[0]['text']  
print(f"Content: {first_document_content[:100]}")    
    
# Generate the content vector using the `generate_document_embeddings` function    
content_vector = generate_document_embeddings(first_document_content)    
print(f"Content vector generated")    
