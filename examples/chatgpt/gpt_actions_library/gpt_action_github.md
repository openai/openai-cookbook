# GPT Action Library: GitHub Pull Requests

## Introduction


This page provides an instruction & guide for developers connecting a GPT Action to GitHub. Before you proceed, make sure to first familiarize yourself with the following information:
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

This GPT Action helps developers evaluate the quality and security of a GitHub Pull Request diff. It provides feedback and suggestions for each domain. Developers can then accept or modify the feedback before automatically submitting it as a comment on the Pull Request.

### Value + Example Business Use Cases

**Value**: Users can now leverage ChatGPT's natural language capabilities to assist with GitHub Pull Request reviews.

- **For developers**: Quickly analyze code changes and perform high-quality reviews with instant feedback on proposed modifications.
- **For organizations**: Ensure that diffs comply with best practices and coding standards, or automatically propose refactored alternatives. 
  - (This would require an additional API request to a "best practices and standards definition.")
- **Overall**: Boost developer productivity and ensure higher quality, more secure code with this AI-powered Code Review assistant.

**Example Use Cases**:
- A user was tagged as a reviewer in a PR and wants a second opinion on the quality and security implications of the proposed change.
- An organization automatically encourages developers to consider adhering to their best practices and standards.

## Application Information

### Application Key Links

Check out these links from the application before you get started:
- Application Website: https://github.com
- Application API Documentation: https://docs.github.com/en/rest/pulls?apiVersion=2022-11-28

### Application Prerequisites

Before you get started, make sure you go through the following steps in your application environment:
- Select a repository with an open pull request.
- Ensure your Personal Access Token is approved for use in the Organization. For OSS or individuals your PAT should work automatically. 

## Application Setup

### Select a Pull Request on a Repository

*   Navigate to any repository, for example https://github.com/microsoft/vscode/pull/229241.
*   Note the Owner: "microsoft", Repository: "vscode" and the PR number: "229241".
*   Understand [_how_ to perform a high quality Code Review.](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/reviewing-proposed-changes-in-a-pull-request)

You can read up on the supported runtimes [here](https://cloud.google.com/functions/docs/concepts/execution-environment)

#### Option 1: Use IDE (VSCode)

See Google's documentation [here](https://cloud.google.com/functions/docs/create-deploy-ide) for how to deploy using VSCode. If you have familiarity with this approach, feel free to use it.


#### Option 2: Directly in Google Cloud Console

See the documentation [here](https://cloud.google.com/functions/docs/console-quickstart) for how to deploy using the Google Cloud Console. 

#### Option 3: Use the Google Cloud CLI (`gcloud`)

See the documentation [here](https://cloud.google.com/functions/docs/create-deploy-gcloud) for how to deploy using the Google Cloud Console. We’ll walk through an example here step by step.


##### Part 1: Install and initialize Google Cloud CLI (`gcloud`)
Follow the steps [here](https://cloud.google.com/sdk/docs/install) that are relevant to the OS you are runnning. The last step of this process is for you to run `gcloud init` and sign in to your Google account

##### Part 2: Setup local development environment
In this example, we will be setting up a Node.js environment.

```
mkdir <directory_name>
cd <directory_name>
```

Initialize the Node.js project

```
npm init
```
Accept the default values for `npm init`

##### Part 3: Create Function
Create the `index.js` file

```
const functions = require('@google-cloud/functions-framework');
const axios = require('axios');

const TOKENINFO_URL = 'https://oauth2.googleapis.com/tokeninfo';

// Register an HTTP function with the Functions Framework that will be executed
// when you make an HTTP request to the deployed function's endpoint.
functions.http('executeGCPFunction', async (req, res) => {
  const authHeader = req.headers.authorization;

  if (!authHeader) {
    return res.status(401).send('Unauthorized: No token provided');
  }

  const token = authHeader.split(' ')[1];
  if (!token) {
    return res.status(401).send('Unauthorized: No token provided');
  }

  try {
    const tokenInfo = await validateAccessToken(token);            
    res.json("You have connected as an authenticated user to Google Functions");
  } catch (error) {
    res.status(401).send('Unauthorized: Invalid token');
  }  
});

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
```
##### Part 4: Deploy Function

This step below will install and add the necessary dependencies in your `package.json` file

```
npm install @google-cloud/functions-framework
npm install axios
```

```
npx @google-cloud/functions-framework --target=executeGCPFunction
```

```
gcloud functions deploy gcp-function-for-chatgpt \
  --gen2 \
  --runtime=nodejs20 \
  --region=us-central1 \
  --source=. \
  --entry-point=executeGCPFunction \
  --trigger-http \
  --allow-unauthenticated
```

## ChatGPT Steps

### Custom GPT Instructions

Once you've created a Custom GPT, copy the text below in the Instructions panel. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) to see how this step works in more detail.

```
When the user asks you to test the integration, you will make a call to the custom action and display the results
```

### OpenAPI Schema

Once you've created a Custom GPT, copy the text below in the Actions panel. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) to see how this step works in more detail.

Below is an example of what connecting to this Middlware might look like. You'll need to insert your application's & function's information in this section.

```javascript
openapi: 3.1.0
info:
  title: {insert title}
  description: {insert description}
  version: 1.0.0
servers:
  - url: {url of your Google Cloud Function}
    description: {insert description}
paths:
  /{your_function_name}:
    get:
      operationId: {create an operationID}
      summary: {insert summary}
      responses:
        '200':
          description: {insert description}
          content:
            text/plain:
              schema:
                type: string
                example: {example of response}
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

You are now ready to test out the GPT. You can enter a simple prompt like "Test Integration" and expect to see the following:

1. Request to sign into Google
2. Allow request to your Google Function
3. Response from ChatGPT showing the response from your function - e.g. "You have connected as an authenticated user to Google Functions"

*Are there integrations that you’d like us to prioritize? Are there errors in our integrations? File a PR or issue in our github, and we’ll take a look.*
