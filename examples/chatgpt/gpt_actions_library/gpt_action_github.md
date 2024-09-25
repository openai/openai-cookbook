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

## Demonstration

<video width="600" controls autoplay>
  <source src="path_to_your_video.mp4" type="video/mp4">
  Your browser does not support the video tag.
</video>

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

### Select a Pull Request on an Organization or individual Repository

*   Navigate to any repository, for example https://github.com/microsoft/vscode/pull/229241.
  *   Note the Owner: "microsoft", Repository: "vscode" and the PR number: "229241".
  *   If the owner is an SSO Organization, your token may [need to be approved](https://docs.github.com/en/organizations/managing-programmatic-access-to-your-organization/managing-requests-for-personal-access-tokens-in-your-organization#managing-fine-grained-personal-access-token-requests) by an Organization administrator before it can access protected resources.
*   Understand [_how_ to perform a high quality Code Review.](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/getting-started/best-practices-for-pull-requests)


##### Generate a GitHub Personal Access Token
* Log in to GitHub and navigate to "Settings" from your profile dropdown.
* Go to "Developer settings" and select "Personal access tokens".
* Click "Generate new token", give it a name, set an expiration date, and select the necessary scopes (read:content, read&write:Pullrequests).
* Click "Generate token", then copy and save the token securely.

## ChatGPT Steps

### Custom GPT Instructions

Once you've created a Custom GPT, copy the text below in the Instructions panel. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) to see how this step works in more detail.

```
# **Context:** You support software developers by providing detailed information about their pull request diff content from repositories hosted on GitHub. You help them understand the quality, security and completeness implications of the pull request by providing concise feedback about the code changes based on known best practices. The developer may elect to post the feedback (possibly with their modifications) back to the Pull Request. Assume the developer is familiar with software development.

# **Instructions:**

## Scenarios
### - When the user asks for information about a specific pull request, follow this 5 step process:
1. If you don't already have it, ask the user to specify the pull request owner, repository and pull request number they want assistance with and the particular area of focus (e.g., code performance, security vulnerabilities, and best practices).
2. Retrieve the Pull Request information from GitHub using the getPullRequestDiff API call, owner, repository and the pull request number provided. 
3. Provide a summary of the pull request diff in four sentences or less then make improvement suggestions where applicable for the particular areas of focus (e.g., code performance, security vulnerabilities, and best practices).
4. Ask the user if they would like to post the feedback as a comment or modify it before posting. If the user modifies the feedback, incorporate that feedback and repeat this step. 
5. If the user confirms they would like the feedback posted as a comment back to the Pull request, use the postPullRequestComment API to comment the feedback on the pull request.
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

### In ChatGPT (refer to Step 2 in the Getting Started Example)

In ChatGPT, click on "Authentication" and choose **"Bearer"**. Enter in the information below.

- **Client ID**: <personal_access_token>

### Back in Google Cloud Console (while referring to Step 4 in the Getting Started Example)

Edit the OAuth 2.0 Client ID you create in Google Cloud earlier and add the callback URL you received after creating your custom action.

![](../../../images/gcp-function-middleware-oauthcallback.png)

### Test the GPT

You are now ready to test out the GPT. You can enter a simple prompt like "Test Integration" and expect to see the following:

1. Request to sign into Google
2. Allow request to your Google Function
3. Response from ChatGPT showing the response from your function - e.g. "You have connected as an authenticated user to Google Functions"

*Are there integrations that you’d like us to prioritize? Are there errors in our integrations? File a PR or issue in our github, and we’ll take a look.*
