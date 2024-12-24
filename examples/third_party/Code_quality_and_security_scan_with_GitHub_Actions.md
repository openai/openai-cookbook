# Code Quality and Security Scan with GitHub Actions

## Introduction

This recipe describes how to integrate OpenAI reasoning models with your CI pipelines to analyze and fortify the quality, security and compliance of code in Pull Requests (PR).

Before you begin, familiarize yourself with the following resources:
- [Introduction to GitHub Actions](https://docs.github.com/en/actions)
- [OpenAI Reasoning Modles](https://platform.openai.com/docs/guides/reasoning)

Although this is a concrete example of how OpenAI can be integrated in a CI pipeline, there are many other ways to integrate AI into your SDLC to accelerate your delivery velocity and improve code quality and security.


## Value & Example Business Use Cases

### **Value**:
Rigorous code reviews, while critical, can often feel time-consuming and tedious for developers. Automating code quality and security scans helps developers focus on meaningful work by reducing manual effort and ensuring consistent feedback on their code. For organizations, this approach saves time and money by addressing issues early, avoiding costly rework, and enforcing best practices across the codebase. Overall, automated code quality and security scans with OpenAI reasoning models enhances productivity, improves code reliability, and fosters a culture of efficiency, benefiting both individual contributors and the broader business.

### **Example Use Cases**:
- A reviewer seeks feedback on the quality and security of a proposed code change.
- An organization encourages adherence to best practices and standards automatically during code review.

## Application Information

### **Prerequisites**
Ensure you have a repository with an open pull request.

## Application Setup

### **Select a Pull Request**
1. Navigate to your GitHub repository, e.g., [example PR](https://github.com/alwell-kevin/OpenAI-Forum/pull/6).
   - Ensure GitHub Actions are enabled for the repository and that you are a Repo Owner, so you can configure [Actions Secrets and Repository Variables](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/store-information-in-variables#creating-configuration-variables-for-a-repository).
2. Review [how to perform a high-quality code review](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/getting-started/best-practices-for-pull-requests).

### **Generate an OpenAI "Project Key" to authenticate your OpenAI API requests**
1. Navigate to platform.openai.com/api-keys.
2. Click to **[Create a new secret key](https://platform.openai.com/api-keys)**.
   1. You will only need "Completions" write permissions under "Model capabilities".
3. Copy and securely store the token.

### **Define Enterprise Coding Standards**

1. If you want to enforce specific coding standards across your organization or repository, you will need to define those standards in plain text. For example:

```
	1.	Code Style & Formatting
	•	Follow standardized, consistent naming conventions (e.g., camelCase or PascalCase for functions and variables).
	•	Use clear and descriptive names for variables, functions, and classes.
	•	Adhere to industry-recognized style guidelines (e.g., PEP 8 for Python or standard ESLint rules for JavaScript).
	•	Maintain consistent indentation and spacing.
	•	Limit line lengths for improved readability (e.g., 80–120 characters).
	2.	Readability & Maintainability
	•	Write self-documenting code: prefer meaningful names, clear function boundaries, and logical structure over excessive comments.
	•	Use comments to clarify non-obvious parts of the logic. Avoid trivial comments.
	•	Organize code into cohesive modules or classes.
	•	Limit function or method sizes to facilitate unit testing, readability, and maintainability.
	3.	Security & Compliance
	•	Validate and sanitize all external inputs to prevent common vulnerabilities (e.g., SQL injection, XSS).
	•	Use secure libraries and frameworks whenever possible.
	•	Store secrets (API keys, credentials) securely and never hard-code them in source files.
	•	Adhere to relevant security standards (e.g., OWASP Top Ten).
	•	Implement proper error handling to avoid revealing sensitive information in logs or error messages.
	4.	Error Handling & Logging
	•	Use structured error handling; log meaningful error messages without exposing sensitive data.
	•	Provide enough context in logs to facilitate debugging and troubleshooting.
	•	Avoid silent catch-all exceptions.
	•	Include fallback or recovery mechanisms where feasible.
	5.	Performance & Scalability
	•	Write efficient code, considering time complexity and resource usage.
	•	Avoid premature optimization; focus first on clarity and correctness.
	•	Use caching, batching, or other techniques as needed for large or frequent operations.
	6.	Testing & Quality Assurance
	•	Include automated unit tests for each major function or module.
	•	Write clear, reproducible tests that reflect real-world usage scenarios.
	•	Use integration tests to verify end-to-end flows when applicable.
	•	Ensure code coverage thresholds (where applicable) are met or exceeded.
	7.	Documentation & Version Control
	•	Include or update relevant documentation (e.g., README, inline docstrings) so others can quickly understand and use the code.
	•	Commit changes regularly with clear commit messages.
	•	Follow your organization’s branching strategy (e.g., GitFlow) for merges and releases.
	8.	Accessibility & Internationalization (when relevant)
	•	Consider accessibility requirements (e.g., WAI-ARIA) for front-end code.
	•	Use frameworks and patterns that support localization/internationalization where necessary.

Instruction to LLM:
	•	Generate only code that adheres to the above conventions.
	•	Avoid shortcuts or hidden assumptions that reduce clarity, maintainability, or security.
	•	When in doubt, err on the side of clarity, safety, and correctness.
	•	When referencing third-party libraries, ensure they are well-established, actively maintained, and meet enterprise security and licensing requirements.
```

2. Store the standards in as a repository variable BEST_PRACTICES in your GitHub repository

![repository_variables.png](../../../images/repository_variables.png)


## GitHub Actions Setup

### **Create a GitHub Actions Workflow**

### OpenAPI Schema

Once you've created a Custom GPT, copy the text below in the Actions panel. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) to see how this step works in more detail.

Below is an example of what connecting to GitHub to GET the Pull Request Diff and POST the Feedback to the Pull Request might look like.

```javascript
openapi: 3.1.0
info:
  title: GitHub Pull Request API
  description: Retrieve the diff of a pull request and post comments back to it.
  version: 1.0.0
servers:
  - url: https://api.github.com
    description: GitHub API
paths:
  /repos/{owner}/{repo}/pulls/{pull_number}:
    get:
      operationId: getPullRequestDiff
      summary: Get the diff of a pull request.
      parameters:
        - name: owner
          in: path
          required: true
          schema:
            type: string
          description: Owner of the repository.
        - name: repo
          in: path
          required: true
          schema:
            type: string
          description: Name of the repository.
        - name: pull_number
          in: path
          required: true
          schema:
            type: integer
          description: The number of the pull request.
        - name: Accept
          in: header
          required: true
          schema:
            type: string
            enum:
              - application/vnd.github.v3.diff
          description: Media type for the diff format.
      responses:
        "200":
          description: Successfully retrieved the pull request diff.
          content:
            text/plain:
              schema:
                type: string
        "404":
          description: Pull request not found.
  /repos/{owner}/{repo}/issues/{issue_number}/comments:
    post:
      operationId: postPullRequestComment
      summary: Post a comment to the pull request.
      parameters:
        - name: owner
          in: path
          required: true
          schema:
            type: string
          description: Owner of the repository.
        - name: repo
          in: path
          required: true
          schema:
            type: string
          description: Name of the repository.
        - name: issue_number
          in: path
          required: true
          schema:
            type: integer
          description: The issue or pull request number.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                body:
                  type: string
                  description: The content of the comment.
      responses:
        "201":
          description: Successfully created a comment.
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: integer
                  body:
                    type: string
                  user:
                    type: object
                    properties:
                      login:
                        type: string
                      id:
                        type: integer
        "404":
          description: Pull request not found.
```

## Authentication Instructions

Below are instructions on setting up authentication with this 3rd party application. Have questions? Check out [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) to see how this step works in more detail.

### In ChatGPT (refer to Step 2 in the Getting Started Example)

In ChatGPT, click on "Authentication" and choose **"Bearer"**. Enter in the information below. Ensure your token has the permissions described in Application setup, above.

- Authentication Type: API Key
- Auth Type: Bearer
- API Key 
  <personal_access_token>

### Test the GPT

You are now ready to test out the GPT. You can enter a simple prompt like "Can you review my pull request? owner: <org_name>, repo: <repo_name>, pull request number: <PR_Number>" and expect to see the following:

![landing_page.png](../../../../images/landing_page.png)

1. A summary of changes in the referenced pull request(PR).

![First Interaction](../../../images/first_interaction.png)

2. Quality and Security feedback and suggestions to incorporate in the next iteration of the PR.

![First Feedback](../../../images/first_feedback.png)

3. An option to iterate on the feedback or accept it and have the GPT post it directly to the PR as a comment from you. 

![First Interaction](../../../images/final_result.png)

*Are there integrations that you’d like us to prioritize? Are there errors in our integrations? File a PR or issue in our github, and we’ll take a look.*