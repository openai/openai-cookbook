# Using Azure Functions with OAuth and Microsoft Graph API to Search O365 / SharePoint from ChatGPT



## Overview

This solution enables a GPT action to answer a user’s question with the context of files the user can access in SharePoint or Office365, using Microsoft’s Graph API [search capabilities](https://learn.microsoft.com/en-us/graph/api/resources/search-api-overview?view=graph-rest-1.0) and the ability to [retrieve files](https://learn.microsoft.com/en-us/graph/api/driveitem-get?view=graph-rest-1.0\&tabs=http). It uses Azure Functions to process the Graph API response and convert it to a human readable format or structure it in a way ChatGPT understands. This code is meant to be directional, and you should modify it to your requirements.


## How it Works

There are two solutions below, with code for each in the repository. 

The first solution **Solution 1** uses the ability to[ retrieve files in Actions](https://platform.openai.com/docs/actions/sending-files) and use them as if you had uploaded them directly to a conversation. The Azure Function returns a base64 string that ChatGPT converts into a file, treated the same way as if you uploaded the file directly to the conversation. This solution can handle more types of files than the other solution below, but does have size volume limitations (see docs [here](https://platform.openai.com/docs/actions/sending-files))

The second solution **Solution 2** pre-processes the file within the Azure Function. The Azure Function returns text, instead of the base64 encoded file. Due to the pre-processing and the conversion to text, this solution is best used for large, unstructured documents, and for when you want to analyze more than the amount of files supported in the first solution (see documentation [here](https://platform.openai.com/docs/actions/sending-files)).


### Solution 1: Returning the file to GPT using the [Returning Files](https://platform.openai.com/docs/actions/sending-files) pattern

![](../../../images/solution_1.gif)

This solution uses a Node.js Azure Function to, based on the logged in user:

1. Search for a relevant file that the user has access to, based on the user’s initial question. 

2. For each file that is found, convert it to a base64 string.

3. Format the data in the structure ChatGPT is expecting [here](https://platform.openai.com/docs/actions/sending-files/inline-option).

4. Return that to ChatGPT. The GPT then can use those files as if you had uploaded it to the conversation.


![](../../../images/solution_1_architecture.png)


### Solution 2: Converting the file to text in the Azure Function


![](../../../images/solution_2.gif)


This solution uses a Node.js Azure Function to, based on the logged in user:

1. Search for a relevant file that the user has access to, based on the user’s initial question.

2. For each file that is found, convert it to a consistent readable format and retrieve all the text.

3. Use GPT 3.5-turbo (gpt-3.5-turbo-0125) to extract the relevant text from the files based on the initial user’s question. Note the pricing of GPT 3.5 turbo [here](https://openai.com/pricing#language-models) - since we are dealing with small token chunks, the cost of this step is nominal.  

4. Returns that data to ChatGPT. The GPT then uses that information to respond to the user's initial question.

As you can see from the below architecture diagram, the first three steps are the same as Solution 1. The main difference is that this solution converts the file to text instead of a base64 string, and then summarizes that text using GPT 3.5 Turbo.


![](../../../images/solution_2_architecture.png)


### Why is this necessary instead of interacting with the Microsoft API directly?

- Following the guide [here](https://learn.microsoft.com/en-us/graph/search-concept-files), the [Microsoft Graph Search API](https://learn.microsoft.com/en-us/graph/search-concept-files) returns references to files that fit the criteria, but not the file contents themselves. So, we need have two options, corresponding to the two solutions above:

  - **Solution 1: restructure the response for compatibility:** 

    1. We need to restructure the response from that API so that it matches the expected structure in `openaiFileResponse` outlined [here](https://platform.openai.com/docs/actions/getting-started/inline-option).

  - **Solution 2: extract the text from the files directly:**

    1. loop through the returned files and download the files using the [Download File endpoint](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0\&tabs=http) or [Convert File endpoint](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format?view=graph-rest-1.0\&tabs=http)

    2. convert that Binary stream to human readable text using [pdf-parse](https://www.npmjs.com/package/pdf-parse)

    3. Then, we can optimize further by summarizing using gpt-3.5-turbo in the function to help with the 100,000 character limit we impose on Actions today. 


## Prerequisites

- Azure Portal with access to create Azure Function Apps and Azure Entra App Registrations

- Postman (and knowledge of APIs and OAuth)

- _Solution 2 Only:_ An OpenAI API Key from platform.openai.com


## Solution 1 + Solution 2 Installation Instructions

The below are the instructions for setting up the Azure Function with Authentication. Please make sure to follow these steps before implementing the code. 

> These installation instructions apply to both Solution 1 and Solution 2. We encourage setting both solutions up as separate functions within the same Function App to test which works best for you, as once you set up one function, it takes only a few minutes to set up another function in that same function app.


### Installing the app

You can read more about languages and deployment options for Azure Functions on the left hand side of the documentation [here](https://learn.microsoft.com/en-us/azure/azure-functions/functions-overview?pivots=programming-language-csharp). 


#### Option 1: Use VSCode

See Microsoft’s documentation [here](https://learn.microsoft.com/en-us/azure/azure-functions/functions-develop-vs-code?tabs=node-v4,python-v2,isolated-process\&pivots=programming-language-javascript) for how to deploy using VSCode. If you have familiarity with this approach, feel free to use it. 


#### Option 2: Directly in Azure Portal

See the documentation [here](https://learn.microsoft.com/en-us/azure/azure-functions/functions-create-function-app-portal?pivots=programming-language-javascript) for how to deploy using the Azure portal. We’ll walk through an example here step by step.

> Note: you can use Part 1 - Part 4 below to set up any Azure Function App with Entra Authentication


##### Part 1: Create Function


![](../../../images/create_function_app.png)


1. Create an [Azure Function app](https://learn.microsoft.com/en-us/azure/azure-functions/functions-overview?pivots=programming-language-csharp). I used the following settings but you can use anything you are comfortable with. Note that not every language / operating system allows for editing the functions in the console directly - the combination I chose below does. For my walkthrough, I left everything as default and made the selections below

   1. Basics

      1. _Do you want to deploy code or container image?:_  **Code**

      2. _Runtime stack:_ **Node.js**

      3. _Operating system:_ **Windows**

   2. Networking

      1. _Enable public access_: **on (need this on to connect to the GPT)**

2. After completing the above, you’ll land on the “Deployments” page. Once the deployment completes (which should only take a few minutes) click on **“Go to Resource”** to go back to the Function App

  > You may get an error the first time you attempt this, click create again and it will likely work. 


##### Part 2: Set up Auth

3. On the left-hand side menu of the Azure Function App, click on **Authentication** under the **Settings** menu. 

   1. Add identity provider

   2. Select **Microsoft** as identity provider. 

   3. **Workforce** as tenant type

   4. **Create a new application.** The instructions are fairly similar if you are using an existing application, but it is easier to create a new application as it will have the callback URLs and the API exposed automatically using “Easy Auth”. You can read more about that [**here**](https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization).

   5. Leave all the other settings on this page as the default, but feel free to change based on your internal guidelines.

   6. On the **permissions** tab, click **Add Permission** and add **Files.Read.All** and **Sites.ReadAll**, then **Add.** This allows this application to read files which is important in order to use the Microsoft Graph Search API.

4. Once it is created, **click on the enterprise application you just created** (so, leave the Function App page and land on the Enterprise Application that you just spun up)**.** We are now going to give it one more permission, to execute the Azure Function by impersonating the user logging into the application. See [here](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad?tabs=workforce-tenant) for more details.

   1. On the main page, click “**View API Permissions”**

   2. Search for **Microsoft Azure App Service** in the **APIs my organization uses** and find **user\_impersonation** 

   3. Add it, then you’ll need an Admin on Azure Portal to **Grant Admin Consent.**

5) **Within that enterprise application**, Click on **“Expose an API”** on the left hand menu under **Manage,** then copy the **scope** that was created using the **Copy to Clipboard** button. The scope should look like “api://\<insert-uuid>/user\_impersonation”. **Save this for later as** `SCOPE`**.**

6) Click on **“Authentication”** on the left hand menu under **Manage**

   1. Under the **Web** section, you’ll notice one callback URI was added automatically. Add the Postman redirect URI (<https://oauth.pstmn.io/v1/callback>) for testing.

7) On the left-hand side, go to **Overview**. Copy the **application (client) ID** and and the **directory (tenant) ID** and **save for later as** `CLIENT_ID` **and** `TENANT_ID`**.**


##### Part 3: Set up Test Function

8. Leave the page by going home and then back to your **Function App.**

9. Click on **Create Function.** For this example, I’m going to develop it in the portal, but you can also use VSCode or another IDE.

   1. Choose **HTTP trigger**

   2. For **Authorization Level,** you can choose any key type you want.

      1. Note this may error out the first time, but it is likely the Function did create, do a refresh of the page to check.

10. Click on the function you just created (You may need to click refresh to see it). Click on **Get Function URL** and save it to test in Postman. You will also use this when creating the OpenAPI spec later when you put it into the GPT. 


![](../../../images/get_function_url.png)

11. Go back to the function app and click on **Configuration.** Show the value for the `MICROSOFT_PROVIDER_AUTHENTICATION_SECRET` variable, copy it (click advanced edit to copy it), and **save it for later.**  

At this point, you should have a test function created, and you should have saved a **client id, tenant id, secret, scope, and function URL**. You are now ready to test out the authentication in Postman


##### Part 4: Test Authentication in Postman

12. Try to hit endpoint you created in Postman using those OAuth settings:

    1. **Grant Type:** Authorization Code

    2. **Auth URL**: [https://login.microsoftonline.com/](about:blank)`TENANT_ID`[/oauth2/v2.0/authorize](about:blank)

    3. **Auth Token URL**: [https://login.microsoftonline.com/`TENANT_ID`/oauth2/v2.0/token](about:blank)

    4. **Client ID:** `CLIENT_ID` from step 7 above

    5. **Client secret:** `MICROSOFT_PROVIDER_AUTHENTICATION_SECRET `from step 11 above

    6. **Scope**: `SCOPE` from step 5 above

    7. **Client credentials**: Send client credentials in body

13. You will need to click **Get New Access Token**, and then hit the endpoint you saved in step 10 above. If it was successful, you should get this response: `”This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.”`


##### Part 5: Add in Function Code

Now that you have an authenticated Azure Function, we can update the function to search SharePoint / O365


14. Go to your test function and paste in the code from [this file](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/sharepoint_azure_function/solution_one_file_retrieval.js) for Solution 1 and [this file](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/sharepoint_azure_function/solution_two_preprocessing.js) for Solution 2.  Save the function. 


> **This code is meant to be directional** - while it should work out of the box, it is designed to be customized to your needs (see examples towards the end of this document).

15. Set up the following env variables by going to the **Configuration** tab on the left under **Settings.** Note that this may be listed directly in **Environment Variables** depending on your Azure UI.

    1. `TENANT_ID`: copied from previous section

    2. `CLIENT_ID`: copied from previous section

    3. _Solution 2 only:_

       1. `OPENAI_API_KEY:` spin up an OpenAI API key on platform.openai.com.

16. Go to the **Console** tab under the **Development Tools**

    1. Install the following packages in console

       1. `npm install @microsoft/microsoft-graph-client`

       2. `npm install axios`

       3. _Solution 2 only:_

          1. `npm install pdf-parse`

          2. `npm install openai`

17. Once this is complete, try calling the function (POST call) from Postman again, putting the below into body (using a query and search term you think will generate responses).

     *Solution 1*:
     ```json
    {
        "searchTerm": "<choose a search term>"
    }
    ```
    *Solution 2*: 
    ```json
    {
        "query": "<choose a question>",
        "searchTerm": "<choose a search term>"
    }
    ```
18. If you get a response, you are ready to set this up with a Custom GPT!


##### Part 6: Setting it up in a Custom GPT

19. Generate an OpenAPI spec for your endpoint. 

20. Paste that into the Actions section of a GPT, and choose OAuth as the authentication type. Fill out the OAuth settings the same way you did for Postman above. 

21. Once you save the action, you will see a callback URI at the bottom of the GPT configuration. Copy that URL, then go **back to your Function App in the Azure Portal**.

22. Click on **Authentication** under **Settings**, then click on your Entra application.

23. Once you are there, then click **Authentication** under the **Manage** section.

24. Add a new Redirect URI under the **Web** section of that page, and paste in the Callback URI you got from step 20, then click Save. 

25. Customize the prompt to use this action. You can see a sample prompt in the Sample GPT Instructions in this document, which is customized to try three times to find an answer by changing the searchTerm. 

26. Test out the GPT and it should work as expected.


## Solution 1 Detailed Walkthrough: Returning the File to GPT using the [Returning Files](https://platform.openai.com/docs/actions/sending-files) Pattern


The below walks through setup instructions and walkthrough unique to this solution. You can find the entire code [here](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/sharepoint_azure_function/solution_one_file_retrieval.js). If you are interested in Solution 2 instead, you can jump [here](#solution-2-converting-the-file-to-text-in-the-azure-function-1). 

### Code Walkthrough

The below walks through the different parts of the function. Before you begin, ensure you have the required packages installed and environment variables set up (see the Installation Steps section).


#### Implementing the Authentication 

Below we have a few helper functions that we’ll use in the function.


##### Initializing the Microsoft Graph Client

Create a function to initialize the Graph client with an access token. This will be used to search through Office 365 and SharePoint.

```javascript
const { Client } = require('@microsoft/microsoft-graph-client');

function initGraphClient(accessToken) {
    return Client.init({
        authProvider: (done) => {
            done(null, accessToken);
        }
    });
}
```

##### Obtaining an On-Behalf-Of (OBO) Token

This function uses an existing bearer token to request an OBO token from Microsoft's identity platform. This enables passing through the credentials to ensure the search only returns files the logged-in user can access.

```javascript
const axios = require('axios');
const qs = require('querystring');

async function getOboToken(userAccessToken) {
    const { TENANT_ID, CLIENT_ID, MICROSOFT_PROVIDER_AUTHENTICATION_SECRET } = process.env;
    const params = {
        client_id: CLIENT_ID,
        client_secret: MICROSOFT\_PROVIDER\_AUTHENTICATION\_SECRET,
        grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        assertion: userAccessToken,
        requested_token_use: 'on_behalf_of',
        scope: 'https://graph.microsoft.com/.default'
    };

    const url = `https\://login.microsoftonline.com/${TENANT_ID}/oauth2/v2.0/token`;
    try {
        const response = await axios.post(url, qs.stringify(params), {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
        });
        return response.data.access\_token;
    } catch (error) {
        console.error('Error obtaining OBO token:', error.response?.data || error.message);
        throw error;
    }
}
```

#### Retrieving Content from O365 / SharePoint Items

This function fetches the content of drive items, converts it to a base64 string, and restructures to match the `openaiFileResponse` format.
```javascript
const getDriveItemContent = async (client, driveId, itemId, name) => {
   try
       const filePath = `/drives/${driveId}/items/${itemId}`;
       const downloadPath = filePath + `/content`
       // this is where we get the contents and convert to base64
       const fileStream = await client.api(downloadPath).getStream();
       let chunks = [];
           for await (let chunk of fileStream) {
               chunks.push(chunk);
           }
       const base64String = Buffer.concat(chunks).toString('base64');
       // this is where we get the other metadata to include in response
       const file = await client.api(filePath).get();
       const mime_type = file.file.mimeType;
       const name = file.name;
       return {"name":name, "mime_type":mime_type, "content":base64String}
   } catch (error) {
       console.error('Error fetching drive content:', error);
       throw new Error(`Failed to fetch content for ${name}: ${error.message}`);
   }
```

#### Creating the Azure Function to Handle Requests

Now that we have all these helper functions, the Azure Function will orchestrate the flow, by authenticating the user, performing the search, and iterating through the search results to extract the text and retrieve the relevant parts of the text to the GPT.

**Handling HTTP Requests:** The function starts by extracting the query and searchTerm from the HTTP request. It checks if the Authorization header is present and extracts the bearer token.

**Authentication:** Using the bearer token, it obtains an OBO token from Microsoft's identity platform using getOboToken defined above.

**Initializing the Graph Client:** With the OBO token, it initializes the Microsoft Graph client using initGraphClient defined above.

**Document Search:** It constructs a search query and sends it to the Microsoft Graph API to find documents based on the searchTerm.

**Document Processing**: For each document returned by the search:

- It retrieves the document content using getDriveItemContent.

- It converts the document to base64 string and restructures it to match the `openaiFileResponse` structure.

**Response**: The function sends them back in the HTTP response.
```javascript
module.exports = async function (context, req) {
   // const query = req.query.query || (req.body && req.body.query);
   const searchTerm = req.query.searchTerm || (req.body && req.body.searchTerm);
   if (!req.headers.authorization) {
       context.res = {
           status: 400,
           body: 'Authorization header is missing'
       };
       return;
   }
   /// The below takes the token passed to the function, to use to get an OBO token.
   const bearerToken = req.headers.authorization.split(' ')[1];
   let accessToken;
   try {
       accessToken = await getOboToken(bearerToken);
   } catch (error) {
       context.res = {
           status: 500,
           body: `Failed to obtain OBO token: ${error.message}`
       };
       return;
   }
   // Initialize the Graph Client using the initGraphClient function defined above
   let client = initGraphClient(accessToken);
   // this is the search body to be used in the Microsft Graph Search API: https://learn.microsoft.com/en-us/graph/search-concept-files
   const requestBody = {
       requests: [
           {
               entityTypes: ['driveItem'],
               query: {
                   queryString: searchTerm
               },
               from: 0,
               // the below is set to summarize the top 10 search results from the Graph API, but can configure based on your documents.
               size: 10
           }
       ]
   };


   try {
       // This is where we are doing the search
       const list = await client.api('/search/query').post(requestBody);
       const processList = async () => {
           // This will go through and for each search response, grab the contents of the file and summarize with gpt-3.5-turbo
           const results = [];
           await Promise.all(list.value[0].hitsContainers.map(async (container) => {
               for (const hit of container.hits) {
                   if (hit.resource["@odata.type"] === "#microsoft.graph.driveItem") {
                       const { name, id } = hit.resource;
                       // The below is where the file lives
                       const driveId = hit.resource.parentReference.driveId;
                       // we use the helper function we defined above to get the contents, convert to base64, and restructure it
                       const contents = await getDriveItemContent(client, driveId, id, name);
                       results.push(contents)
               }
           }));
           return results;
       };
       let results;
       if (list.value[0].hitsContainers[0].total == 0) {
           // Return no results found to the API if the Microsoft Graph API returns no results
           results = 'No results found';
       } else {
           // If the Microsoft Graph API does return results, then run processList to iterate through.
           results = await processList();
           // this is where we structure the response so ChatGPT knows they are files
           results = {'openaiFileResponse': results}
       }
       context.res = {
           status: 200,
           body: results
       };
   } catch (error) {
       context.res = {
           status: 500,
           body: `Error performing search or processing results: ${error.message}`,
       };
   }
};
```
### Customizations

Below are some potential areas to customize. 

- You can customize the GPT prompt to search again a certain amount of times if nothing is found.

- You can customize the code to only search through specific SharePoint sites or O365 Drives by customizing the search query. This will help focus the search and improve the retrieval. The function as setup now looks through all files the logged-in user can access.

- You can update the code to only return certain types of files. For example, only return structured data / CSVs. 

- You can customize the amount of files it searches through within the call to Microsoft Graph. Note that you should only put a maximum of 10 files based on the documentation [here](https://platform.openai.com/docs/actions/getting-started). 

### Considerations

Note that all the same limitations of Actions apply here, with regards to returning 100K characters or less and the [45 second timeout](https://platform.openai.com/docs/actions/production/timeouts).

- Make sure you read the documentation here around [returning files](https://platform.openai.com/docs/actions/sending-files) and [file uploads](https://help.openai.com/en/articles/8555545-file-uploads-faq), as those limitations apply here.

### Sample GPT Instructions


```text
You are a Q&A helper that helps answer users questions. You have access to a documents repository through your API action. When a user asks a question, you pass in the "searchTerm" a single keyword or term you think you should use for the search.

****

Scenario 1: There are answers

If your action returns results, then you take the results from the action and try to answer the users question. 

****

Scenario 2: No results found

If the response you get from the action is "No results found", stop there and let the user know there were no results and that you are going to try a different search term, and explain why. You must always let the user know before conducting another search.

Example:

****

I found no results for "DEI". I am now going to try [insert term] because [insert explanation]

****

Then, try a different searchTerm that is similar to the one you tried before, with a single word. 

Try this three times. After the third time, then let the user know you did not find any relevant documents to answer the question, and to check SharePoint. 
Be sure to be explicit about what you are searching for at each step.

****

In either scenario, try to answer the user's question. If you cannot answer the user's question based on the knowledge you find, let the user know and ask them to go check the HR Docs in SharePoint. 
```
### Sample OpenAPI Spec
This expects a response that matches the file retrieval structure in our doc [here](https://platform.openai.com/docs/actions/sending-files) and passes in a `searchTerm` parameter to inform the search.
>Make sure to switch the function app name, function name and code based on link copied in screenshot [here](#part-3-set-up-test-function)

```yaml
openapi: 3.0.0
info:
  title: SharePoint Search API
  description: API for searching SharePoint documents.
  version: 1.0.0
servers:
  - url: https://{your_function_app_name}.azurewebsites.net/api
    description: SharePoint Search API server
paths:
  /{your_function_name}?code={enter your specific endpoint id here}:
    post:
      operationId: searchSharePoint
      summary: Searches SharePoint for documents matching a query and term.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                searchTerm:
                  type: string
                  description: A specific term to search for within the documents.
      responses:
        '200':
          description: A CSV file of query results encoded in base64.
          content:
            application/json:
              schema:
                type: object
                properties:
                  openaiFileResponseData:
                    type: array
                    items:
                      type: object
                      properties:
                        name:
                          type: string
                          description: The name of the file.
                        mime_type:
                          type: string
                          description: The MIME type of the file.
                        content:
                          type: string
                          format: byte
                          description: The base64 encoded contents of the file.
        '400':
          description: Bad request when the SQL query parameter is missing.
        '413':
          description: Payload too large if the response exceeds the size limit.
        '500':
          description: Server error when there are issues executing the query or encoding the results.
```

## Solution 2 Detailed Walkthrough: Converting the file to text in the Azure Function


The below walks through setup instructions and walkthrough unique to this solution of pre-processing the files and extracting summaries in the Azure Function. You can find the entire code [here](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/sharepoint_azure_function/solution_two_preprocessing.js).

### Code Walkthrough

#### Implementing the Authentication 

This solution follows the same authentication steps as solution 1 above - see [Initializing the Microsoft Graph Client](#initializing-the-microsoft-graph-client) and [Obtaining an On-Behalf-Of (OBO) Token](#obtaining-an-on-behalf-of-obo-token) sections.


#### Retrieving Content from O365 / SharePoint Items

This function fetches the content of drive items, handling different file types and converting files to PDF when necessary for text extraction. This uses the [download endpoint](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0\&tabs=http) for PDFs and the [convert endpoint](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format?view=graph-rest-1.0\&tabs=http) for other supported file types.
```javascript
const getDriveItemContent = async (client, driveId, itemId, name) => {
    try {
        const fileType = path.extname(name).toLowerCase();
        // the below files types are the ones that are able to be converted to PDF to extract the text. See https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format?view=graph-rest-1.0&tabs=http
        const allowedFileTypes = ['.pdf', '.doc', '.docx', '.odp', '.ods', '.odt', '.pot', '.potm', '.potx', '.pps', '.ppsx', '.ppsxm', '.ppt', '.pptm', '.pptx', '.rtf'];
        // filePath changes based on file type, adding ?format=pdf to convert non-pdf types to pdf for text extraction, so all files in allowedFileTypes above are converted to pdf
        const filePath = `/drives/${driveId}/items/${itemId}/content` + ((fileType === '.pdf' || fileType === '.txt' || fileType === '.csv') ? '' : '?format=pdf');
        if (allowedFileTypes.includes(fileType)) {
            response = await client.api(filePath).getStream();
            // The below takes the chunks in response and combines
            let chunks = [];
            for await (let chunk of response) {
                chunks.push(chunk);
            }
            let buffer = Buffer.concat(chunks);
            // the below extracts the text from the PDF.
            const pdfContents = await pdfParse(buffer);
            return pdfContents.text;
        } else if (fileType === '.txt') {
            // If the type is txt, it does not need to create a stream and instead just grabs the content
            response = await client.api(filePath).get();
            return response;
        }  else if (fileType === '.csv') {
            response = await client.api(filePath).getStream();
            let chunks = [];
            for await (let chunk of response) {
                chunks.push(chunk);
            }
            let buffer = Buffer.concat(chunks);
            let dataString = buffer.toString('utf-8');
            return dataString
            
    } else {
        return 'Unsupported File Type';
    }
     
    } catch (error) {
        console.error('Error fetching drive content:', error);
        throw new Error(`Failed to fetch content for ${name}: ${error.message}`);
    }
};
```

#### Integrating GPT 3.5-Turbo for Text Analysis

This function utilizes the OpenAI SDK to analyze text extracted from documents and find relevant information based on a user query. This helps to ensure only relevant text to the user’s question is returned to the GPT. 

```javascript
const getRelevantParts = async (text, query) => {
    try {
        // We use your OpenAI key to initialize the OpenAI client
        const openAIKey = process.env["OPENAI_API_KEY"];
        const openai = new OpenAI({
            apiKey: openAIKey,
        });
        const response = await openai.chat.completions.create({
            // Using gpt-3.5-turbo due to speed to prevent timeouts. You can tweak this prompt as needed
            model: "gpt-3.5-turbo-0125",
            messages: [
                {"role": "system", "content": "You are a helpful assistant that finds relevant content in text based on a query. You only return the relevant sentences, and you return a maximum of 10 sentences"},
                {"role": "user", "content": `Based on this question: **"${query}"**, get the relevant parts from the following text:*****\n\n${text}*****. If you cannot answer the question based on the text, respond with 'No information provided'`}
            ],
            // using temperature of 0 since we want to just extract the relevant content
            temperature: 0,
            // using max_tokens of 1000, but you can customize this based on the number of documents you are searching. 
            max_tokens: 1000
        });
        return response.choices[0].message.content;
    } catch (error) {
        console.error('Error with OpenAI:', error);
        return 'Error processing text with OpenAI' + error;
    }
};
```

#### Creating the Azure Function to Handle Requests

Now that we have all these helper functions, the Azure Function will orchestrate the flow, by authenticating the user, performing the search, and iterating through the search results to extract the text and retrieve the relevant parts of the text to the GPT.

**Handling HTTP Requests:** The function starts by extracting the query and searchTerm from the HTTP request. It checks if the Authorization header is present and extracts the bearer token.

**Authentication:** Using the bearer token, it obtains an OBO token from Microsoft's identity platform using getOboToken defined above.

**Initializing the Graph Client:** With the OBO token, it initializes the Microsoft Graph client using initGraphClient defined above.

**Document Search:** It constructs a search query and sends it to the Microsoft Graph API to find documents based on the searchTerm.

**Document Processing**: For each document returned by the search:

- It retrieves the document content using getDriveItemContent.

- If the file type is supported, it analyzes the content using getRelevantParts, which sends the text to OpenAI's model for extracting relevant information based on the query.

- It collects the analysis results and includes metadata like the document name and URL.

**Response**: The function sorts the results by relevance and sends them back in the HTTP response.

```javascript
module.exports = async function (context, req) {
    const query = req.query.query || (req.body && req.body.query);
    const searchTerm = req.query.searchTerm || (req.body && req.body.searchTerm);
    if (!req.headers.authorization) {
        context.res = {
            status: 400,
            body: 'Authorization header is missing'
        };
        return;
    }
    /// The below takes the token passed to the function, to use to get an OBO token.
    const bearerToken = req.headers.authorization.split(' ')[1];
    let accessToken;
    try {
        accessToken = await getOboToken(bearerToken);
    } catch (error) {
        context.res = {
            status: 500,
            body: `Failed to obtain OBO token: ${error.message}`
        };
        return;
    }
    // Initialize the Graph Client using the initGraphClient function defined above
    let client = initGraphClient(accessToken);
    // this is the search body to be used in the Microsft Graph Search API: https://learn.microsoft.com/en-us/graph/search-concept-files
    const requestBody = {
        requests: [
            {
                entityTypes: ['driveItem'],
                query: {
                    queryString: searchTerm
                },
                from: 0,
                // the below is set to summarize the top 10 search results from the Graph API, but can configure based on your documents. 
                size: 10
            }
        ]
    };

    try { 
        // Function to tokenize content (e.g., based on words). 
        const tokenizeContent = (content) => {
            return content.split(/\s+/);
        };

        // Function to break tokens into 10k token windows for gpt-3.5-turbo
        const breakIntoTokenWindows = (tokens) => {
            const tokenWindows = []
            const maxWindowTokens = 10000; // 10k tokens
            let startIndex = 0;

            while (startIndex < tokens.length) {
                const window = tokens.slice(startIndex, startIndex + maxWindowTokens);
                tokenWindows.push(window);
                startIndex += maxWindowTokens;
            }

            return tokenWindows;
        };
        // This is where we are doing the search
        const list = await client.api('/search/query').post(requestBody);

        const processList = async () => {
            // This will go through and for each search response, grab the contents of the file and summarize with gpt-3.5-turbo
            const results = [];

            await Promise.all(list.value[0].hitsContainers.map(async (container) => {
                for (const hit of container.hits) {
                    if (hit.resource["@odata.type"] === "#microsoft.graph.driveItem") {
                        const { name, id } = hit.resource;
                        // We use the below to grab the URL of the file to include in the response
                        const webUrl = hit.resource.webUrl.replace(/\s/g, "%20");
                        // The Microsoft Graph API ranks the reponses, so we use this to order it
                        const rank = hit.rank;
                        // The below is where the file lives
                        const driveId = hit.resource.parentReference.driveId;
                        const contents = await getDriveItemContent(client, driveId, id, name);
                        if (contents !== 'Unsupported File Type') {
                            // Tokenize content using function defined previously
                            const tokens = tokenizeContent(contents);

                            // Break tokens into 10k token windows
                            const tokenWindows = breakIntoTokenWindows(tokens);

                            // Process each token window and combine results
                            const relevantPartsPromises = tokenWindows.map(window => getRelevantParts(window.join(' '), query));
                            const relevantParts = await Promise.all(relevantPartsPromises);
                            const combinedResults = relevantParts.join('\n'); // Combine results

                            results.push({ name, webUrl, rank, contents: combinedResults });
                        } 
                        else {
                            results.push({ name, webUrl, rank, contents: 'Unsupported File Type' });
                        }
                    }
                }
            }));

            return results;
        };
        let results;
        if (list.value[0].hitsContainers[0].total == 0) {
            // Return no results found to the API if the Microsoft Graph API returns no results
            results = 'No results found';
        } else {
            // If the Microsoft Graph API does return results, then run processList to iterate through.
            results = await processList();
            results.sort((a, b) => a.rank - b.rank);
        }
        context.res = {
            status: 200,
            body: results
        };
    } catch (error) {
        context.res = {
            status: 500,
            body: `Error performing search or processing results: ${error.message}`,
        };
    }
};
```

### Customizations

Below are some potential areas to customize. 

- You can customize the GPT prompt to search again a certain amount of times if nothing is found.

- You can customize the code to only search through specific SharePoint sites or O365 Drives by customizing the search query. This will help focus the search and improve the retrieval. The function as setup now looks through all files the logged-in user can access.

- You could use gpt-4o instead of gpt-3.5 turbo for longer context. This would slightly increase the cost and latency, but you may get higher quality summarizations.

- You can customize the amount of files it searches through within the call to Microsoft Graph.


### Considerations

Note that all the same limitations of Actions apply here, with regards to returning 100K characters or less and the [45 second timeout](https://platform.openai.com/docs/actions/production/timeouts).


- This only works for text, not for images. With some additional code in the Azure Function, you could customize this by using GPT-4o to extract summarizations of images.

- This does not work for structured data. We recommend Solution 1 if structured data is a major part of your use case.

### Sample GPT Instructions


```
You are a Q&A helper that helps answer users questions. You have access to a documents repository through your API action. When a user asks a question, you pass in that question exactly as stated to the "query" parameter, and for the "searchTerm" you use a single keyword or term you think you should use for the search.

****

Scenario 1: There are answers

If your action returns results, then you take the results from the action and summarize concisely with the webUrl returned from the action. You answer the users question to the best of your knowledge from the action

****

Scenario 2: No results found

If the response you get from the action is "No results found", stop there and let the user know there were no results and that you are going to try a different search term, and explain why. You must always let the user know before conducting another search.

Example:

****

I found no results for "DEI". I am now going to try [insert term] because [insert explanation]

****

Then, try a different searchTerm that is similar to the one you tried before, with a single word. 

Try this three times. After the third time, then let the user know you did not find any relevant documents to answer the question, and to check SharePoint. Be sure to be explicit about what you are searching for at each step.

****

In either scenario, try to answer the user's question. If you cannot answer the user's question based on the knowledge you find, let the user know and ask them to go check the HR Docs in SharePoint. If the file is a CSV, XLSX, or XLS, you can tell the user to download the file using the link and re-upload to use Advanced Data Analysis.
```

### Sample OpenAPI Spec
The below spec passes in the `query` parameter to inform the pre-processing and a `searchTerm` to find the right files in Microsoft Graph.
>Make sure to switch the function app name, function name and code based on link copied in screenshot [here](#part-3-set-up-test-function)

```yaml
openapi: 3.0.0
info:
  title: SharePoint Search API
  description: API for searching SharePoint documents.
  version: 1.0.0
servers:
  - url: https://{your_function_app_name}.azurewebsites.net/api
    description: SharePoint Search API server
paths:
  /{your_function_name}?code={enter your specific endpoint id here}:
    post:
      operationId: searchSharePoint
      summary: Searches SharePoint for documents matching a query and term.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                query:
                  type: string
                  description: The full query to search for in SharePoint documents.
                searchTerm:
                  type: string
                  description: A specific term to search for within the documents.
      responses:
        '200':
          description: Search results
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    documentName:
                      type: string
                      description: The name of the document.
                    snippet:
                      type: string
                      description: A snippet from the document containing the search term.
                    url:
                      type: string
                      description: The URL to access the document.
```


## FAQ

- Why are you using the Microsoft Graph API in your code instead of the [SharePoint API](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/get-to-know-the-sharepoint-rest-service?tabs=csom)?

  - The SharePoint API is legacy - per the Microsoft documentation [here](https://learn.microsoft.com/en-us/sharepoint/dev/apis/sharepoint-rest-graph), “For SharePoint Online, innovation using a REST API against SharePoint is driven via the Microsoft Graph REST API's.” The Graph API gives us more flexibility, and the SharePoint API still runs into the same file issues listed in the [Why is this necessary instead of interacting with the Microsoft Graph API directly?](#why-is-this-necessary-instead-of-interacting-with-the-microsoft-api-directly) section.

- What types of files does this support?

  - _Solution 1:_ 

    1. It follows the same guidelines as the documentation [here](https://help.openai.com/en/articles/8555545-file-uploads-faq) about file uploads. 

  - _Solution 2:_ 

    1. This supports all files listed in the documentation for the Convert File endpoint [_here_](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format?view=graph-rest-1.0\&tabs=http). Specifically, it supports _pdf, doc, docx, odp, ods, odt, pot, potm, potx, pps, ppsx, ppsxm, ppt, pptm, pptx, rtf_.

    2. When a search result returns XLS, XLSX, or CSV, this prompts the user to download the file and re-upload to ask questions using Advanced Data Analysis. As stated above, we recommend solution 1 if structured data is part of your use case.

- Why do I need to request an OBO token?

  - When you try to use the same token to authenticate to the Graph API as the one you use to authenticate into the Azure Function, you get an “invalid audience” token. This is because the audience for the token can only be user\_impersonation.

  - To address this, the function requests a new token scoped to Files.Read.All within the app using the [On Behalf Of flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow). This will inherit the permissions of the logged in user, meaning this function will only search through files the logged-in user has access to. 

  - We are purposefully requesting a new On Behalf Of token with each request, because Azure Function Apps are meant to be stateless. You could potentially integrate this with Azure Key Vault to store the secret and retrieve programmatically. 




