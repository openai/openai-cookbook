# File Q&A

File Q&A is a [Next.js](https://nextjs.org/) app that lets you find answers in your files using OpenAI APIs. You can upload files and ask questions related to their content, and the app will use embeddings and GPT to generate answers from the most relevant files.

## Requirements

To run the app, you need an OpenAI API key. You can create a new API key [here](https://beta.openai.com/account/api-keys).

## Set Up

If you don't have Node.js and npm already, install them from [https://nodejs.org/en/download/](https://nodejs.org/en/download/).

In your terminal, navigate to the `nextjs` directory of this example app, and then install dependencies:

```
npm install
```

Copy the .env.local.example file into a .env.local file and fill out the OpenAI API key field.

## Development

Run the development server:

```
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the app.

## Deployment

You can deploy the app on [Vercel](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme), the platform from the creators of Next.js. Check out the [Next.js deployment documentation](https://nextjs.org/docs/deployment) for more details.

## Limitations

Uploaded files and generated embeddings don't persist on browser refresh. If you want to store more embeddings, we recommend using a vector database (e.g. Pinecone, Weaviate, Milvus, Qdrant, Redis, FAISS, etc.). The `nextjs-with-flask-server` version of this demo uses a Pinecone vector database.

The app may sometimes generate answers that are not in the files, or hallucinate about the existence of files that are not uploaded.
