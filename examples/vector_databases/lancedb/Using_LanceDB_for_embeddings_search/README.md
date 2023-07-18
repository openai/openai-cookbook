## Using LanceDB for Embeddings Search

This example takes you through a simple flow to download some data, embed it, and then index and search it using a selection of vector databases. This is a common requirement for customers who want to store and search our embeddings with their own data in a secure environment to support production use cases such as chatbots, topic modelling and more.

### What is a Vector Database

A vector database is a database made to store, manage and search embedding vectors. The use of embeddings to encode unstructured data (text, audio, video and more) as vectors for consumption by machine-learning models has exploded in recent years, due to the increasing effectiveness of AI in solving use cases involving natural language, image recognition and other unstructured forms of data. Vector databases have emerged as an effective solution for enterprises to deliver and scale these use cases.

### Why use a Vector Database

Vector databases enable enterprises to take many of the embeddings use cases we've shared in this repo (question and answering, chatbot and recommendation services, for example), and make use of them in a secure, scalable environment. Many of our customers make embeddings solve their problems at small scale but performance and security hold them back from going into production - we see vector databases as a key component in solving that, and in this guide we'll walk through the basics of embedding text data, storing it in a vector database and using it for semantic search.

### What is LanceDB?
LanceDB is a serverless vector database that makes data management for LLMs frictionless. It has multi-modal search, native Python and JS support, and many ecosystem integrations. Learn more about LanceDB [here](https://lancedb.com).

### Demo Flow
The demo flow is:
- **Setup**: Import packages and set any required variables
- **Load data**: Load a dataset and embed it using OpenAI embeddings
- **LanceDB**
    - *Setup*: Here we'll set up the Python client for LanceDB. For more details go [here](https://lancedb.github.io/lancedb/basic/)
    - *Index Data*: We'll create a table and index it for __titles__. For `main.py` and `index.js` this will only occur on the first run.
    - *Search Data*: Run a few example queries with various goals in mind.

Once you've run through this example you should have a basic understanding of how to setup and use vector databases, and can move on to more complex use cases making use of our embeddings.
Colab walkthrough - <a href="https://colab.research.google.com/github/openai/openai-cookbook/blob/main/examples/vector_databases/lancedb/Using_LanceDB_for_embeddings_search/main.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a>

### Python
Install dependencies
```bash
pip install -r requirements.txt
```

Run the script 
```python
python main.py --query "Important battles related to the American Revolutionary War"
```
default query = `Important battles related to the American Revolutionary War`

| Argument | Default Value | Description |
|---|---|---|
| query | "Important battles ..." | Query to search |
| top-k | `5` | Number of results to show |
| openai-key | | OpenAI API Key, not required if `OPENAI_API_KEY` env var is set  |
| model | `text-embedding-ada-002` | OpenAI embedding model to use |

### Javascript
Install dependencies
```bash
npm install
```

Run the script
```bash
wget -c https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip
unzip vector_database_wikipedia_articles_embedded.zip -d data/
```

```javascript
OPENAI_API_KEY=... node index.js
```
