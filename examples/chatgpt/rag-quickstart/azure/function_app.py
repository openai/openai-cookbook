import azure.functions as func
import json
import logging
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.core.credentials import AzureKeyCredential
from openai import OpenAI
import os
from azure.search.documents.models import (
    VectorizedQuery
)

# Initialize the Azure Function App
app = func.FunctionApp()

def generate_embeddings(text):
    # Check if text is provided
    if not text:
        logging.error("No text provided in the query string.")
        return func.HttpResponse(
            "Please provide text in the query string.",
            status_code=400
        )

    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        logging.info("OpenAI client initialized successfully.")
        
        # Generate embeddings using OpenAI API
        response = client.embeddings.create(
            input=text,
            model=os.getenv("EMBEDDINGS_MODEL")
        )
        logging.info("Embeddings created successfully.")
        
        # Extract the embedding from the response
        embedding = response.data[0].embedding
        logging.debug(f"Generated embedding: {embedding}")
        
        return embedding
    except Exception as e:
        logging.error(f"Error generating embeddings: {str(e)}")
        return func.HttpResponse(
            f"Error generating embeddings: {str(e)}",
            status_code=500
        )


@app.route(route="vector_similarity_search", auth_level=func.AuthLevel.ANONYMOUS)
def vector_similarity_search(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Received request for vector similarity search.")
    try:
        # Parse the request body as JSON
        req_body = req.get_json()
        logging.info("Request body parsed successfully.")
    except ValueError:
        logging.error("Invalid JSON in request body.")
        return func.HttpResponse(
            "Invalid JSON in request body.",
            status_code=400
        )

    # Extract parameters from the request body
    search_service_endpoint = req_body.get('search_service_endpoint')
    index_name = req_body.get('index_name')
    query = req_body.get('query')
    k_nearest_neighbors = req_body.get('k_nearest_neighbors')
    search_column = req_body.get('search_column')
    use_hybrid_query = req_body.get('use_hybrid_query')
    
    logging.info(f"Parsed request parameters: search_service_endpoint={search_service_endpoint}, index_name={index_name}, query={query}, k_nearest_neighbors={k_nearest_neighbors}, search_column={search_column}, use_hybrid_query={use_hybrid_query}")

    # Generate embeddings for the query
    embeddings = generate_embeddings(query)
    logging.info(f"Generated embeddings: {embeddings}")

    # Check for required parameters
    if not (search_service_endpoint and index_name and query):
        logging.error("Missing required parameters in request body.")
        return func.HttpResponse(
            "Please provide search_service_endpoint, index_name, and query in the request body.",
            status_code=400
        )
    try:
        # Create a vectorized query
        vector_query = VectorizedQuery(vector=embeddings, k_nearest_neighbors=float(k_nearest_neighbors), fields=search_column)
        logging.info("Vector query generated successfully.")
    except Exception as e:
        logging.error(f"Error generating vector query: {str(e)}")
        return func.HttpResponse(
            f"Error generating vector query: {str(e)}",
            status_code=500
        )

    try:
        # Initialize the search client
        search_client = SearchClient(
            endpoint=search_service_endpoint,
            index_name=index_name,
            credential=AzureKeyCredential(os.getenv("SEARCH_SERVICE_API_KEY"))
        )
        logging.info("Search client created successfully.")
        
        # Initialize the index client and get the index schema
        index_client = SearchIndexClient(endpoint=search_service_endpoint, credential=AzureKeyCredential(os.getenv("SEARCH_SERVICE_API_KEY"))) 
        index_schema = index_client.get_index(index_name)
        for field in index_schema.fields:
            logging.info(f"Field: {field.name}, Type: {field.type}")
        # Filter out non-vector fields
        non_vector_fields = [field.name for field in index_schema.fields if field.type not in ["Edm.ComplexType", "Collection(Edm.ComplexType)","Edm.Vector","Collection(Edm.Single)"]]

        logging.info(f"Non-vector fields in the index: {non_vector_fields}")
    except Exception as e:
        logging.error(f"Error creating search client: {str(e)}")
        return func.HttpResponse(
            f"Error creating search client: {str(e)}",
            status_code=500
        )

    # Determine if hybrid query should be used
    search_text = query if use_hybrid_query else None

    try:
        # Perform the search
        results = search_client.search(  
            search_text=search_text,  
            vector_queries=[vector_query],
            select=non_vector_fields,
            top=3
        )
        logging.info("Search performed successfully.")
    except Exception as e:
        logging.error(f"Error performing search: {str(e)}")
        return func.HttpResponse(
            f"Error performing search: {str(e)}",
            status_code=500
        )

    try:
        # Extract relevant data from results and put it into a list of dictionaries
        response_data = [result for result in results]
        response_data = json.dumps(response_data)
        logging.info("Search results processed successfully.")
    except Exception as e:
        logging.error(f"Error processing search results: {str(e)}")
        return func.HttpResponse(
            f"Error processing search results: {str(e)}",
            status_code=500
        )

    logging.info("Returning search results.")
    return func.HttpResponse(response_data, mimetype="application/json")
