# GPT Action Library: MongoDB Atlas Vector Search

## Introduction


This page provides an instruction & guide for developers building a GPT Action for a specific application. Before you proceed, make sure to first familiarize yourself with the following information:

- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

This particular GPT Action provides an overview of how to connect to MongoDB Atlas. This Action takes a user’s question and generates MQL to perform a semantic search on a particlar collection to answer the user’s question. It uses Google Cloud Run Functions and OpenAI's Embeddings API to transform the user query to an embedding that will be used as a query parameter for the semantic search.

### Value + Example Business Use Cases

**Value**: Users can now leverage ChatGPT's natural language capability to connect directly to MongoDB Atlas and perform a semantic search. 

**Example Use Cases**:

- A user needs to perform a vector search in MongoDB, but needs a middleware app between ChatGPT and Google Cloud SQL

- A user has thousands of files and has gone through the process of vectorizing the files and storing them in MongoDB

## Application Information

### Application Key Links

Check out these links before you get started:

- OpenAI Embeddings API - https://platform.openai.com/docs/guides/embeddings
- MongoDB Atlas Vector Search - https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/

### Application Prerequisites

Before you get started, make sure you go through the following steps in your application environment:

- An OpenAI API key
- Access to a MongoDB Atlas cluster
- Google Cloud Console with access to create Google Cloud Run Functions and Google Cloud APIs (you will need this to set up the OAuth Client)

## Middleware Information

### Middleware Function

To create a Google Run Function, follow the steps in the [GCP Functions Action](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_google_cloud_function) cookbook.

To deploy specifically an application that connects to MongoDB Atlas, use the following code instead of the `index.js` file that is referenced in the Middleware GCP Functions cookbook. You can take the code pasted below and modify it to your needs.

> This code is meant to be directional - while it should work out of the box, it is designed to be customized to your needs.

```
const functions = require('@google-cloud/functions-framework');
const axios = require('axios');
const { MongoClient } = require('mongodb');
const OpenAI = require('openai');
require('dotenv').config(); // Load env variables from .env file

// Initialize OpenAI API with API key
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY // Use the API key from environment variables
});

// Use the full MongoDB connection string from the environment variable
const uri = process.env.MONGODB_URI;

const client = new MongoClient(uri);

const TOKENINFO_URL = 'https://oauth2.googleapis.com/tokeninfo';

// Function to validate the access token using Google OAuth
async function validateAccessToken(token) {
  try {
    const response = await axios.get(TOKENINFO_URL, {
      params: {
        access_token: token,
      },
    });
    return response.data;
  } catch (error) {
    throw new Error('Invalid token');
  }
}

async function searchMongoDB(aggPipeline) {
  try {
    await client.connect();
    
    // Get the database name and collection name from environment variables
    const database = client.db(process.env.MONGODB_DB_NAME); // Using the database name from env
    const collection = database.collection(process.env.MONGODB_COLLECTION_NAME); // Using the collection name from env

    // Perform the aggregation with the provided pipeline
    const result = await collection.aggregate(aggPipeline).toArray();

    return result;
  } finally {
    await client.close();
  }
}

// Function to get embeddings from OpenAI
async function getEmbedding(searchTerm) {
  try {
    const embeddingResponse = await openai.embeddings.create({
      model: process.env.OPENAI_MODEL, // Specify the embedding model from env
      input: searchTerm,
    });

    const embedding = embeddingResponse.data[0].embedding;
    return embedding;
  } catch (error) {
    console.error("Error getting embedding from OpenAI:", error);
    throw error;
  }
}

// Main function to handle the HTTP request and authenticate users
functions.http('queryVectorDB', async (req, res) => {
  const authHeader = req.headers.authorization;

  if (!authHeader) {
    return res.status(401).send('Unauthorized: No token provided');
  }

  const token = authHeader.split(' ')[1];
  if (!token) {
    return res.status(401).send('Unauthorized: No token provided');
  }

  try {
    // Validate the access token
    await validateAccessToken(token);

    // Proceed with your logic after successful authentication
    const searchTerm = req.body.searchTerm || "";
    if (typeof searchTerm !== 'string' || searchTerm.trim().length === 0) {
      return res.status(400).send("Invalid searchTerm: it must be a non-empty string.");
    }

    // Get the query vector from OpenAI
    const queryVector = await getEmbedding(searchTerm);

    // Define the aggregation pipeline for vector search - switch this out to match your collection
    const aggPipeline = [
      {
        '$vectorSearch': {
          'index': process.env.MONGODB_VECTOR_INDEX, // Your vector index name from env
          'path': 'plot_embedding', // Path to the vector field in your documents
          'queryVector': queryVector, // The vector from OpenAI
          'numCandidates': 150, // Number of candidates to consider
          'limit': 10 // Limit the number of results returned
        }
      },
      {
        '$project': {
          '_id': 0,
          'plot': 1,
          'title': 1,
          'score': {
            '$meta': 'vectorSearchScore' // Include the vector search score
          }
        }
      }
    ];

    // Perform the search using MongoDB
    const results = await searchMongoDB(aggPipeline);
    res.status(200).json(results);

  } catch (error) {
    console.error("Authentication or search error:", error);
    res.status(401).send('Unauthorized: Invalid token or internal error');
  }
});

```

Make sure you have included these dependencies

```
  "dependencies": {
    "@google-cloud/functions-framework": "^3.4.2",
    "axios": "^1.7.7",
    "dotenv": "^16.4.5",
    "mongodb": "^6.8.0",
    "openai": "^4.62.1"
  }
```
Your `.env` file should contain the following values

```
OPENAI_API_KEY=
MONGODB_URI=
MONGODB_DB_NAME=
MONGODB_COLLECTION_NAME=
OPENAI_MODEL=
MONGODB_VECTOR_INDEX=
```

## Application Setup

### Create vector index

Ensure that your MongoDB collection has a vector index. Here is an example of how to create one

```
db.<collectionName>.createSearchIndex(
  "vector_index", 
  "vectorSearch", 
  {
    "fields": [
      {
        "type": "vector",
        "path": <fieldName>,
        "numDimensions": 1536,
        "similarity": "euclidean"
      }
    ]
  }
);
```

## ChatGPT Steps

### Custom GPT Instructions

Once you've created a Custom GPT, copy the text below in the Instructions panel. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) to see how this step works in more detail.

```
Trigger: User types in a description of a movie they want to find
Instructions:

1) Get the description of the movie that the user is looking for and pass it as "searchTerm" to the custom action "searchDatabase"
2) Retrieve the response from the custom action and display the movies to the user
```

### OpenAPI Schema

Once you've created a Custom GPT, copy the text below in the Actions panel. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) to see how this step works in more detail.

Below is an example of what connecting to this Middlware might look like. You'll need to insert your application's & function's information in this section.

```javascript
openapi: 3.1.0
info:
  title: MongoDB Vector Search API
  description: API for searching movie plots and titles based on a search term.
  version: 1.0.0
servers:
  - url: https://us-central1-enhanced-storm-404515.cloudfunctions.net
    description: Main production server
paths:
  /girish-mongo-search:
    post:
      operationId: searchDatabase
      summary: Search for movies based on a search term.
      description: |
        This endpoint accepts a search term and returns a list of movies with their plot, title, and a relevance score.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                searchTerm:
                  type: string
                  description: The term to search for in movie plots and titles.
              required:
                - searchTerm
      responses:
        '200':
          description: A list of movies matching the search term.
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    plot:
                      type: string
                      description: The plot of the movie.
                    title:
                      type: string
                      description: The title of the movie.
                    score:
                      type: number
                      format: float
                      description: The relevance score of the movie.
        '400':
          description: Bad request. Occurs if the request body is malformed or missing required fields.
        '500':
          description: Internal server error. Occurs if there is a server-side issue.

```

## Authentication Instructions

Below are instructions on setting up authentication with this 3rd party application. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) to see how this step works in more detail.


### In Google Cloud Console
In Google Cloud Console, you need to create OAuth client ID credentials. To navigate to the right page search for "Credentials" in Google Cloud Console or enter `https://console.cloud.google.com/apis/credentials?project=<your_project_id>` in your browser. You can read more about it [here](https://developers.google.com/workspace/guides/create-credentials).

Click on "CREATE CREDENTIALS" and select "Oauth client ID". Select "Web Application" for "Application type" and enter the name of your application (see below).

![](../../../images/gcp-function-middleware-oauthclient.png)

In the "OAuth client created" modal dialog, please take note of the

* Client ID
* Client secret


### In ChatGPT (refer to Step 2 in the Getting Started Example)

In ChatGPT, click on "Authentication" and choose **"OAuth"**. Enter in the information below.

- **Client ID**: *see step above*
- **Client Secret**: *see step above*
- **Authorization URL**: `https://accounts.google.com/o/oauth2/auth`
- **Token URL**: `https://oauth2.googleapis.com/token`
- **Scope**: `https://www.googleapis.com/auth/userinfo.email`

### Back in Google Cloud Console (while referring to Step 4 in the Getting Started Example)

Edit the OAuth 2.0 Client ID you create in Google Cloud earlier and add the callback URL you received after creating your custom action.

![](../../../images/gcp-function-middleware-oauthcallback.png)

### Test the GPT

You are now ready to test out the GPT. You can enter a simple prompt like "I want to watch movies that involve spies and world war" and expect to see the following:

1. Request to sign into Google
2. Allow request to your Google Function
3. Response from ChatGPT showing the response from your function - e.g.

```
Here are some movies that involve spies and World War themes:

Sharpe's Sword: During the Napoleonic wars, Sharpe must protect a vital spy while facing threats from French spies and personal issues.

P-51 Dragon Fighter: Set during World War II, this film follows the Allies as they face off against the Nazis' secret weapon—dragons.

Victory: Allied POWs plan an escape while preparing for a soccer game against the German National Team in Nazi-occupied Paris.

Walking with the Enemy: A young man disguises himself as a Nazi officer during World War II to find his family and uncovers much more.

The Spy: In 1941, a group of soldiers and a spy must rescue a hostage held by a German agent during World War II.

Let me know if any of these catch your eye!
```

*Are there integrations that you’d like us to prioritize? Are there errors in our integrations? File a PR or issue in our github, and we’ll take a look.*
