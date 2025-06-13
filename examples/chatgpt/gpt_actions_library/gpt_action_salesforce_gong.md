# GPT Action Library: Salesforce + Gong

## Introduction

This page provides an instruction & guide for developers building middleware to connect a GPT Action to a specific application. Before you proceed, make sure to first familiarize yourself with the following information:

- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

This particular GPT Action provides an overview of how to build a GPT that retrieves information from Salesforce and Gong. This will include creating multiple custom actions which are documented in existing cookbooks. We will highlight these cookbooks in the next section.

### Value + Example Business Use Cases

**Value**: Users can now leverage ChatGPT's capabilities to:

- Connect to Salesforce
- Search for customer accounts
- Retrieve Gong transcripts from previous calls

**Example Use Cases**:

A sales rep is preparing for an upcoming customer meeting. Using this integration, they can quickly retrieve relevant account details from Salesforce, access recent Gong call transcripts, and receive AI-generated summaries and insights structured around proven sales methodologies like MEDPICC or SPICED. This empowers the rep with a clear, actionable understanding of the customer's current state and next steps — all in minutes

## Application Information
In this example, we are connecting to Salesforce and Gong (via a middleware). We are going to refer to existing cookbooks for basic setup and authentication instructions for Salesforce and creating a middleware. 

### Salesforce GPT Action

Refer to our cookbook on setting up a GPT Action for Salesforce. The two settings to pay attention to in that cookbook are:

- [Application Information](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_salesforce#application-information) - this covers the necessary concepts to be familiar with in Salesforce
- [Authentication Instructions](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_salesforce#authentication-instructions) - this covers creating a Connected App in Salesforce and configuring OAuth (on both Salesforce and ChatGPT)

### Middleware GPT Action
Refer to any one of our cookbooks on creating a middleware:

- [GPT Actions library (Middleware) - AWS](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_aws_function)
- [GPT Actions library (Middleware) - Azure Functions](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function)
- [GPT Actions library (Middleware) - Google Cloud Function](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_google_cloud_function)

### Application Prerequisites

In addition to the prerequisites in the cookbooks above, please ensure that you have access to a Gong API key 

## Application Setup

### Deploying a serverless function

This serverless function will accept an array of `callIds`, fetch the transcripts from Gong and clean up the response that it sends to ChatGPT. Here is an example of what it looks like on Azure Functions (Javascript)

```javascript
const { app } = require('@azure/functions');
const axios = require('axios');

// Replace with your Gong API token
const GONG_API_BASE_URL = "https://api.gong.io/v2";
const GONG_API_KEY = process.env.GONG_API_KEY;

app.http('callTranscripts', {
    methods: ['POST'],
    authLevel: 'function',
    handler: async (request, context) => {        
        try {            
            const body = await request.json();
            const callIds = body.callIds;

            if (!Array.isArray(callIds) || callIds.length === 0) {
                return {
                    status: 400,
                    body: "Please provide call IDs in the 'callIds' array."
                };
            }

            // Fetch call transcripts
            const transcriptPayload = { filter: { callIds } };
            const transcriptResponse = await axios.post(`${GONG_API_BASE_URL}/calls/transcript`, transcriptPayload, {
                headers: {
                    'Authorization': `Basic ${GONG_API_KEY}`,
                    'Content-Type': 'application/json'
                }
            });

            const transcriptData = transcriptResponse.data;

            // Fetch extensive call details
            const extensivePayload = {
                filter: { callIds },
                contentSelector: {
                    exposedFields: { parties: true }
                }
            };

            const extensiveResponse = await axios.post(`${GONG_API_BASE_URL}/calls/extensive`, extensivePayload, {
                headers: {
                    'Authorization': `Basic ${GONG_API_KEY}`,
                    'Content-Type': 'application/json'
                }
            });

            const extensiveData = extensiveResponse.data;

            // Create a map of call IDs to metadata and speaker details
            const callMetaMap = {};
            extensiveData.calls.forEach(call => {
                callMetaMap[call.metaData.id] = {
                    title: call.metaData.title,
                    started: call.metaData.started,
                    duration: call.metaData.duration,
                    url: call.metaData.url,
                    speakers: {}
                };

                call.parties.forEach(party => {
                    callMetaMap[call.metaData.id].speakers[party.speakerId] = party.name;
                });
            });

            // Transform transcript data into content and include metadata
            transcriptData.callTranscripts.forEach(call => {
                const meta = callMetaMap[call.callId];
                if (!meta) {
                    throw new Error(`Metadata for callId ${call.callId} not found.`);
                }

                let content = '';
                call.transcript.forEach(segment => {
                    const speakerName = meta.speakers[segment.speakerId] || "Unknown Speaker";

                    // Combine all sentences for the speaker into a paragraph
                    const sentences = segment.sentences.map(sentence => sentence.text).join(' ');
                    content += `${speakerName}: ${sentences}\n\n`; // Add a newline between speaker turns
                });

                // Add metadata and content to the call object
                call.title = meta.title;
                call.started = meta.started;
                call.duration = meta.duration;
                call.url = meta.url;
                call.content = content;
                
                delete call.transcript;
            });

            // Return the modified transcript data
            return {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(transcriptData)
            };
        } catch (error) {
            context.log('[ERROR]', "Error processing request:", error);

            return {
                status: error.response?.status || 500,
                body: {
                    message: "An error occurred while fetching or processing call data.",
                    details: error.response?.data || error.message
                }
            };
        }
    }
});

```

Here are the dependencies that you would include in your `package.json` file

```javascript
"dependencies": {
    "@azure/functions": "^4.0.0",
    "axios": "^1.7.7"
  }
```

## ChatGPT Steps

### Custom GPT Instructions

Once you've created a Custom GPT, copy the text below in the Instructions panel. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) to see how this step works in more detail.

```
# Trigger
User enters the name of an account that they want to prepare for

# Steps
1. Retrieve Account Names - Make a call to the `executeSOSLSearch` custom action searching for a Salesforce Account with that name (SOSL). Retrieve up to 5 accounts. This is what the query should look like - `FIND {Acme} IN ALL FIELDS RETURNING Account(Id, Name) LIMIT 5`

2. Show the accounts in this format - `Account Name - salesforceID`. Ask the user to confirm which account they are interested in. 

3. Get Gong Call IDs for the account - For the confirmed account, make a call to `executeSOQLQuery` to get all the Gong Call IDs. It should look like this - `SELECT XXX, YYY, ZZZ
FROM Gong__Gong_Call__c 
WHERE Gong__Primary_Account__c = '<AccountId>' 
ORDER BY Gong__Call_Start__c DESC 
LIMIT 2
`

4. Pass in the callIds to `getTranscriptsByCallIds `

# Trigger
User says "Summarize call"

# Steps

Use both the transcripts and provide the following output

## Account Name
Print out the account name 

## Details of calls
>Please list the calls for which you retrieved the transcripts along with their dates and attendees in this table format:  
>>Headers: <Title of Call>, <Date>, <Attendees>, <Gong URL>

## Recommended Meeting Focus Areas: 
>Analyze the transcripts to identify themes, challenges, and opportunities. Based on this, generate a list of recommended focus areas for the next meeting. These should be actionable and specific to the client’s needs. Explain **why** each item should be a meeting focus.

For each of the following insights, specify **which call and date** you sourced the insight from:

### Metrics
Quantifiable outcomes the customer is trying to achieve. These could be cost reduction, increased revenue, user growth, efficiency gains, etc. Look for KPIs or success measures mentioned.

### Economic Buyer
Identify if the true economic decision-maker was mentioned or involved. This includes titles, names, or hints at budget ownership or final authority.

### Decision Criteria
What are the key factors the customer will use to evaluate solutions? These could include price, performance, support, integrations, ease of use, etc.

### Decision Process
Describe how the customer plans to make the buying decision: stages, stakeholders involved, approval processes, timelines.

### Paper Process
Any mention of legal, procurement, compliance, or contract-related steps and timelines should be captured here.

### Identify Pain
Highlight the core business challenges the customer is facing, ideally in their own words. Understand what’s driving urgency.

### Champion
Is there someone internally who is championing our solution? Mention names, roles, or behaviors that indicate advocacy (e.g., “I’m pushing this internally”).

### (Optional) Competition
Mention any competing vendors, internal builds, or alternative solutions discussed.
```
In the above example, replace the query in (3) to retrieves the Gong Call IDs from your custom Salesforce object.

You will now create 2 separate actions - one to connect to Salesforce and the other to connect to the middleware that calls the Gong APIs

### OpenAPI Schema for Salesforce custom action

Once you've created a Custom GPT, copy the text below in the Actions panel. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) to see how this step works in more detail.

Below is an example of what connecting to Salesforce might look like. You'll need to insert your URL in this section.

```javascript
openapi: 3.1.0
info:
  title: Salesforce API
  version: 1.0.0
  description: API for accessing Salesforce sObjects and executing queries.
servers:
  - url: https://<subdomain>.my.salesforce.com/services/data/v59.0
    description: Salesforce API server
paths:
  /query:
    get:
      summary: Execute a SOQL Query
      description: Executes a given SOQL query and returns the results.
      operationId: executeSOQLQuery
      parameters:
        - name: q
          in: query
          description: The SOQL query string to be executed.
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Query executed successfully.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/QueryResult'

  /search:
    get:
      summary: Execute a SOSL Search
      description: Executes a SOSL search based on the given query and returns matching records.
      operationId: executeSOSLSearch
      parameters:
        - name: q
          in: query
          description: The SOSL search string (e.g., 'FIND {Acme}').
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Search executed successfully.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SearchResult'

components:
  schemas:
    QueryResult:
      type: object
      description: Result of a SOQL query.
      properties:
        totalSize:
          type: integer
          description: The total number of records matching the query.
        done:
          type: boolean
          description: Indicates if the query result includes all records.
        records:
          type: array
          description: The list of records returned by the query.
          items:
            $ref: '#/components/schemas/SObject'

    SearchResult:
      type: object
      description: Result of a SOSL search.
      properties:
        searchRecords:
          type: array
          description: The list of records matching the search query.
          items:
            $ref: '#/components/schemas/SObject'

    SObject:
      type: object
      description: A Salesforce sObject, which represents a database table record.
      properties:
        attributes:
          type: object
          description: Metadata about the sObject, such as type and URL.
          properties:
            type:
              type: string
              description: The sObject type.
            url:
              type: string
              description: The URL of the record.
        Id:
          type: string
          description: The unique identifier for the sObject.
      additionalProperties: true
```

### Authentication instructions for Salesforce custom actions
Please follow the steps shown in [GPT Actions library - Salesforce](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_salesforce#in-chatgpt)

### OpenAPI Schema for the middleware that connects to Gong
In this example, we are setting this up for an Azure Function that calls the Gong APIs. Replace `url` with your own Middleware URL

```
openapi: 3.1.0
info:
  title: Call Transcripts API
  description: API to retrieve call transcripts and associated metadata by specific call IDs.
  version: 1.0.1
servers:
  - url: https://<subdomain>.azurewebsites.net/api
    description: Production server
paths:
  /callTranscripts:
    post:
      operationId: getTranscriptsByCallIds
      x-openai-isConsequential: false
      summary: Retrieve call transcripts by call IDs
      description: Fetches specific call transcripts based on the provided call IDs in the request body.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                callIds:
                  type: array
                  description: List of call IDs for which transcripts need to be fetched.
                  items:
                    type: string
              required:
                - callIds
      responses:
        '200':
          description: A successful response containing the requested call transcripts and metadata.
          content:
            application/json:
              schema:
                type: object
                properties:
                  requestId:
                    type: string
                    description: Unique request identifier.
                  records:
                    type: object
                    description: Metadata about the pagination.
                    properties:
                      totalRecords:
                        type: integer
                        description: Total number of records available.
                      currentPageSize:
                        type: integer
                        description: Number of records in the current page.
                      currentPageNumber:
                        type: integer
                        description: The current page number.
                  callTranscripts:
                    type: array
                    description: List of call transcripts.
                    items:
                      type: object
                      properties:
                        callId:
                          type: string
                          description: Unique identifier for the call.
                        title:
                          type: string
                          description: Title of the call or meeting.
                        started:
                          type: string
                          format: date-time
                          description: Timestamp when the call started.
                        duration:
                          type: integer
                          description: Duration of the call in seconds.
                        url:
                          type: string
                          format: uri
                          description: URL to access the call recording or details.
                        content:
                          type: string
                          description: Transcript content of the call.
        '400':
          description: Invalid request. Possibly due to missing or invalid `callIds` parameter.
        '401':
          description: Unauthorized access due to invalid or missing API key.
        '500':
          description: Internal server error.
```


*Are there integrations that you’d like us to prioritize? Are there errors in our integrations? File a PR or issue in our github, and we’ll take a look.*
