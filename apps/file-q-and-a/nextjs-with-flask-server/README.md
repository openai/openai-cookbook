# File Q&A with Next.js and Flask

File Q&A is a web app that lets you find answers in your files. You can upload files and ask questions related to their content, and the app will use embeddings and GPT to generate answers from the most relevant files. \

## Requirements

To run the app, you need:

- An OpenAI API key. You can create a new API key [here](https://beta.openai.com/account/api-keys).
- A Pinecone API key and index name. You can create a new account and index [here](https://www.pinecone.io/).
- Python 3.7 or higher and pipenv for the Flask server.
- Node.js and npm for the Next.js client.

## Set-Up and Development

### Server

Fill out the config.yaml file with your Pinecone API key, index name and environment.

Run the Flask server:

```
cd server
bash script/start "<your OPENAI_API_KEY>"
```

### Client

Navigate to the client directory and install Node dependencies:

```
cd client
npm install
```

Run the Next.js client:

```
cd client
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the app.

## Limitations

The app may sometimes generate answers that are not in the files, or hallucinate about the existence of files that are not uploaded.
