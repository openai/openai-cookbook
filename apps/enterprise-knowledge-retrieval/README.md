# Enterprise Knowledge Retrieval

This app is a deep dive on Enterprise Knowledge Retrieval, which aims to take some unstructured text documents and create a usable knowledge base application with it.

This repo contains a notebook and a basic Streamlit app:
- `enterprise_knowledge_retrieval.ipynb`: A notebook containing a step by step process of tokenising, chunking and embedding your data in a vector database, building a chat agent on top and running a basic evaluation of its performance.
- `chatbot.py`: A Streamlit app providing simple Q&A via a search bar to query your knowledge base.

To run the app, please follow the instructions below in the ```App``` section

## Notebook

The notebook is the best place to start, and takes you through an end-to-end workflow for setting up and evaluating a simple back-end knowledge retrieval service:
- **Setup:** Initiate variables and connect to a vector database.
- **Storage:** Configure the database, prepare our data and store embeddings and metadata for retrieval.
- **Search:** Extract relevant documents back out with a basic search function and use an LLM to summarise results into a concise reply.
- **Answer:** Add a more sophisticated agent which will process the user's query and maintain a memory for follow-up questions.
- **Evaluate:** Take question/answer pairs using our service, evaluate and plot them to scope out remedial action

Once you've run the notebook through to the Search stage, you should have what you need to set up and run the app.

## App

We've rolled in a basic Streamlit app that you can interact with to test your retrieval service using either standard semantic search or [HyDE](https://arxiv.org/abs/2212.10496) retrievals.

To use it:
- Ensure you followed the Setup and Storage steps from the notebook to populate a vector database with searchable content.
- Set up a virtual environment with pip by running ```virtualenv venv``` (ensure ```virtualenv``` is installed).
- Activate the environment by running ```source venv/bin/activate```.
- Install requirements by running ```pip install -r requirements.txt```.
- Run ```streamlit run chatbot.py``` to fire up the Streamlit app in your browser.

## Limitations

- This app uses Redis as a vector database, but there are many other options highlighted `../examples/vector_databases` depending on your need.
- We introduce many areas you may optimize in the notebook, but we'll deep dive on these in subsequent cookbooks.