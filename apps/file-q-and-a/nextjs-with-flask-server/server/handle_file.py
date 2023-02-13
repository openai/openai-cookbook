import logging
import sys
import docx2txt

from PyPDF2 import PdfReader
from numpy import array, average
from flask import current_app
from config import *

from utils import get_embeddings, get_pinecone_id_for_file_chunk

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# Handle a file by extracting its text, creating embeddings, and upserting them to Pinecone
def handle_file(file, session_id, pinecone_index, tokenizer):
    """Handle a file by extracting its text, creating embeddings, and upserting them to Pinecone."""
    filename = file.filename
    logging.info("[handle_file] Handling file: {}".format(filename))

    # Get the file text dict from the current app config
    file_text_dict = current_app.config["file_text_dict"]

    # Extract text from the file
    try:
        extracted_text = extract_text_from_file(file)
    except ValueError as e:
        logging.error(
            "[handle_file] Error extracting text from file: {}".format(e))
        raise e

    # Save extracted text to file text dict
    file_text_dict[filename] = extracted_text

    # Handle the extracted text as a string
    return handle_file_string(filename, session_id, extracted_text, pinecone_index, tokenizer, file_text_dict)

# Extract text from a file based on its mimetype
def extract_text_from_file(file):
    """Return the text content of a file."""
    if file.mimetype == "application/pdf":
        # Extract text from pdf using PyPDF2
        reader = PdfReader(file)
        extracted_text = ""
        for page in reader.pages:
            extracted_text += page.extract_text()
    elif file.mimetype == "text/plain":
        # Read text from plain text file
        extracted_text = file.read().decode("utf-8")
        file.close()
    elif file.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        # Extract text from docx using docx2txt
        extracted_text = docx2txt.process(file)
    else:
        # Unsupported file type
        raise ValueError("Unsupported file type: {}".format(file.mimetype))

    return extracted_text

# Handle a file string by creating embeddings and upserting them to Pinecone
def handle_file_string(filename, session_id, file_body_string, pinecone_index, tokenizer, file_text_dict):
    """Handle a file string by creating embeddings and upserting them to Pinecone."""
    logging.info("[handle_file_string] Starting...")

    # Clean up the file string by replacing newlines and double spaces
    clean_file_body_string = file_body_string.replace(
        "\n", "; ").replace("  ", " ")
    # Add the filename to the text to embed
    text_to_embed = "Filename is: {}; {}".format(
        filename, clean_file_body_string)

    # Create embeddings for the text
    try:
        text_embeddings, average_embedding = create_embeddings_for_text(
            text_to_embed, tokenizer)
        logging.info(
            "[handle_file_string] Created embedding for {}".format(filename))
    except Exception as e:
        logging.error(
            "[handle_file_string] Error creating embedding: {}".format(e))
        raise e

    # Get the vectors array of triples: file_chunk_id, embedding, metadata for each embedding
    # Metadata is a dict with keys: filename, file_chunk_index
    vectors = []
    for i, (text_chunk, embedding) in enumerate(text_embeddings):
        id = get_pinecone_id_for_file_chunk(session_id, filename, i)
        file_text_dict[id] = text_chunk
        vectors.append(
            (id, embedding, {"filename": filename, "file_chunk_index": i}))

        logging.info(
            "[handle_file_string] Text chunk {}: {}".format(i, text_chunk))

    # Split the vectors array into smaller batches of max length 2000
    batch_size = MAX_PINECONE_VECTORS_TO_UPSERT_PATCH_SIZE
    batches = [vectors[i:i+batch_size] for i in range(0, len(vectors), batch_size)]

    # Upsert each batch to Pinecone
    for batch in batches:
        try:
            pinecone_index.upsert(
                vectors=batch, namespace=session_id)

            logging.info(
                "[handle_file_string] Upserted batch of embeddings for {}".format(filename))
        except Exception as e:
            logging.error(
                "[handle_file_string] Error upserting batch of embeddings to Pinecone: {}".format(e))
            raise e

# Compute the column-wise average of a list of lists
def get_col_average_from_list_of_lists(list_of_lists):
    """Return the average of each column in a list of lists."""
    if len(list_of_lists) == 1:
        return list_of_lists[0]
    else:
        list_of_lists_array = array(list_of_lists)
        average_embedding = average(list_of_lists_array, axis=0)
        return average_embedding.tolist()

# Create embeddings for a text using a tokenizer and an OpenAI engine
def create_embeddings_for_text(text, tokenizer):
    """Return a list of tuples (text_chunk, embedding) and an average embedding for a text."""
    token_chunks = list(chunks(text, TEXT_EMBEDDING_CHUNK_SIZE, tokenizer))
    text_chunks = [tokenizer.decode(chunk) for chunk in token_chunks]

    # Split text_chunks into shorter arrays of max length 10
    text_chunks_arrays = [text_chunks[i:i+MAX_TEXTS_TO_EMBED_BATCH_SIZE] for i in range(0, len(text_chunks), MAX_TEXTS_TO_EMBED_BATCH_SIZE)]

    # Call get_embeddings for each shorter array and combine the results
    embeddings = []
    for text_chunks_array in text_chunks_arrays:
        embeddings_response = get_embeddings(text_chunks_array, EMBEDDINGS_MODEL)
        embeddings.extend([embedding["embedding"] for embedding in embeddings_response])

    text_embeddings = list(zip(text_chunks, embeddings))

    average_embedding = get_col_average_from_list_of_lists(embeddings)

    return (text_embeddings, average_embedding)

# Split a text into smaller chunks of size n, preferably ending at the end of a sentence
def chunks(text, n, tokenizer):
    tokens = tokenizer.encode(text)
    """Yield successive n-sized chunks from text."""
    i = 0
    while i < len(tokens):
        # Find the nearest end of sentence within a range of 0.5 * n and 1.5 * n tokens
        j = min(i + int(1.5 * n), len(tokens))
        while j > i + int(0.5 * n):
            # Decode the tokens and check for full stop or newline
            chunk = tokenizer.decode(tokens[i:j])
            if chunk.endswith(".") or chunk.endswith("\n"):
                break
            j -= 1
        # If no end of sentence found, use n tokens as the chunk size
        if j == i + int(0.5 * n):
            j = min(i + n, len(tokens))
        yield tokens[i:j]
        i = j
