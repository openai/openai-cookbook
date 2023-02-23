# File Q&A

File Q&A is a [Next.js](https://nextjs.org/) app that lets you find answers in your files using OpenAI APIs. You can upload files and ask questions related to their content, and the app will use embeddings and GPT to generate answers from the most relevant files.

This repo contains two versions of the app:

- `/nextjs`: A standalone Next.js app that stores embeddings locally in the browser. You will need an OpenAI API key to use this app. Read more in its [README](./nextjs/README.md).
- `/nextjs-with-flask-server`: A Next.js app that uses a Flask server as a proxy to access the OpenAI APIs, and Pinecone as a vector database to store embeddings. You will need an OpenAI API key and a Pinecone API key to use this app. Read more in its [README](./nextjs-with-flask-server/README.md).

To run either version of the app, please follow the instructions in the respective README.md files in the subdirectories.

## How it works

When a file is uploaded, text is extracted from the file. This text is then split into shorter text chunks, and an embedding is created for each text chunk. When the user asks a question, an embedding is created for the question, and a similarity search is performed to find the file chunk embeddings that are most similar to the question (i.e. have highest cosine similarities with the question embedding). An API call is then made to the completions endpoint, with the question and the most relevant file chunks are included in the prompt. The generative model then gives the answer to the question found in the file chunks, if the answer can be found in the extracts.

## Limitations

The app may sometimes generate answers that are not in the files, or hallucinate about the existence of files that are not uploaded.
