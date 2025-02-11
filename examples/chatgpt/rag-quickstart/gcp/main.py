from google.cloud import bigquery
import functions_framework
import os
from openai import OpenAI
import json

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
embeddings_model = os.getenv('EMBEDDINGS_MODEL')
project_id = os.getenv('PROJECT_ID')
dataset_id = os.getenv('DATASET_ID')
table_id = os.getenv('TABLE_ID')

def generate_embeddings(text, model):
    print(f'Generating embedding for: {text}')
    # Generate embeddings for the provided text using the specified model
    embeddings_response = openai_client.embeddings.create(model=model, input=text)
    # Extract the embedding data from the response
    embedding = embeddings_response.data[0].embedding
    return embedding

@functions_framework.http
def openai_docs_search(request):
    print('received a request')
    client = bigquery.Client()
    
    request_json = request.get_json(silent=True)
    print(request_json)
    
    if not request_json:
        return json.dumps({"error": "Invalid JSON in request"}), 400, {'Content-Type': 'application/json'}
    
    query = request_json.get('query')
    top_k = request_json.get('top_k', 3)
    category = request_json.get('category', '')

    if not query:
        return json.dumps({"error": "Query parameter is required"}), 400, {'Content-Type': 'application/json'}
    
    embedding_query = generate_embeddings(query, embeddings_model)
    embedding_query_list = ', '.join(map(str, embedding_query))
    
    sql_query = f"""
    WITH search_results AS (
        SELECT query.id AS query_id, base.id AS base_id, distance
        FROM VECTOR_SEARCH(
            TABLE `{project_id}.{dataset_id}.{table_id}`, 'content_vector',
            (SELECT ARRAY[{embedding_query_list}] AS content_vector, 'query_vector' AS id),
            top_k => {top_k}, distance_type => 'COSINE', options => '{{"use_brute_force": true}}')
    )
    SELECT sr.query_id, sr.base_id, sr.distance, ed.text, ed.title, ed.category
    FROM search_results sr
    JOIN `{project_id}.{dataset_id}.{table_id}` ed ON sr.base_id = ed.id
    """
    
    if category:
        sql_query += f" WHERE ed.category = '{category}'"

    sql_query += " ORDER BY sr.distance;"
    
    query_job = client.query(sql_query)  # Make an API request.
    
    rows = []
    for row in query_job:
        print(row.title)
        rows.append({
            "text": row.text,
            "title": row.title,
            "distance": row.distance,
            "category": row.category
        })

    response = {
        "items": rows
    }
    print('sending response')
    print(len(rows))
    return json.dumps(response), 200