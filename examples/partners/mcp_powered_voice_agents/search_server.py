import os
from mcp.server.fastmcp import FastMCP
from openai import OpenAI
from agents import set_tracing_export_api_key

# Create server
mcp = FastMCP("Search Server")
_vector_store_id = ""

def _run_rag(query: str) -> str:
    """Do a search for answers within the knowledge base and internal documents of the user.
    Args:
        query: The user query
    """
    results = client.vector_stores.search(
        vector_store_id=_vector_store_id,
        query=query,
        rewrite_query=True,  # Query rewriting generally improves results
    )
    return results.data[0].content[0].text


def _summarize_rag_response(rag_output: str) -> str:
    """Summarize the RAG response using GPT-4
    Args:
        rag_output: The RAG response
    """
    response = client.responses.create(
        model="gpt-4.1-mini",
        tools=[{"type": "web_search_preview"}],
        input="Summarize the following text concisely: \n\n" + rag_output,
    )
    return response.output_text


@mcp.tool()
def generate_rag_output(query: str) -> str:
    """Generate a summarized RAG output for a given query.
    Args:
        query: The user query
    """
    print("[debug-server] generate_rag_output: ", query)
    rag_output = _run_rag(query)
    return _summarize_rag_response(rag_output)


@mcp.tool()
def run_web_search(query: str) -> str:
    """Run a web search for the given query.
    Args:
        query: The user query
    """
    print("[debug-server] run_web_search:", query)
    response = client.responses.create(
        model="gpt-4.1-mini",
        tools=[{"type": "web_search_preview"}],
        input=query,
    )
    return response.output_text


def index_documents(directory: str):
    """Index the documents in the given directory to the vector store
    Args:
        directory: The directory to index the documents from
    """
    # OpenAI supported file extensions for retrieval (see docs)
    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.md', '.docx', '.pptx', '.csv', '.rtf', '.html', '.json', '.xml'}
    # Collect all files in the specified directory
    files = [os.path.join(directory, f) for f in os.listdir(directory)]
    # Filter files for supported extensions only
    supported_files = []
    for file_path in files:
        _, ext = os.path.splitext(file_path)
        if ext.lower() in SUPPORTED_EXTENSIONS:
            supported_files.append(file_path)
        else:
            print(f"[warning] Skipping unsupported file for retrieval: {file_path}")

    vector_store = client.vector_stores.create( # Create vector store
        name="Support FAQ",
    )
    global _vector_store_id
    _vector_store_id = vector_store.id

    for file_path in supported_files:
        # Upload each file to the vector store, ensuring the file handle is closed
        with open(file_path, "rb") as fp:
            client.vector_stores.files.upload_and_poll(
                vector_store_id=vector_store.id,
                file=fp
            )
        print(f"[debug-server] uploading file: {file_path}")


if __name__ == "__main__":
    oai_api_key = os.environ.get("OPENAI_API_KEY")
    if not oai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    set_tracing_export_api_key(oai_api_key)
    client = OpenAI(api_key=oai_api_key)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    samples_dir = os.path.join(current_dir, "sample_files")
    index_documents(samples_dir)

    mcp.run(transport="sse")
