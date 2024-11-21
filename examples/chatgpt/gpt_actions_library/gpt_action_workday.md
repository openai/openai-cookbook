# **Workday GPT Action Cookbook**

## **Table of Contents**

1. [General App Information](#general-app-information)  
2. [Authentication from ChatGPT to Workday](#authentication-from-chatgpt-to-workday)  
3. [Sample Use Case: PTO Submission and Benefit Plan Inquiry](#sample-use-case-pto-submission-and-benefit-plan-inquiry)  
4. [Additional Resources](#additional-resources)  
5. [Conclusion](#conclusion)

## General App Information

Workday is a cloud-based platform that offers solutions for human capital management, payroll, and financial management. Integrating ChatGPT with Workday through Custom Actions can enhance HR operations by providing automated responses to employee inquiries, guiding employees through HR processes, and retrieving key information from Workday.

ChatGPT’s Custom Actions with Workday allow organizations to use AI to improve HR processes, automate tasks, and offer personalized employee support. This includes virtual HR assistants for inquiries about benefits, time off, and payroll.

## Authentication from ChatGPT to Workday

To connect ChatGPT with Workday, use OAuth:

* Requires Workday Admin access to obtain Client ID and Client Secret.  
* Important URLs:  
    * **Authorization URL**: `[Workday Tenant URL]/authorize`, typically in this format: `https://wd5-impl.workday.com/<your_tenant>/authorize`  
    * **Token URL**: `[Workday Tenant URL]/token`, typically in this format: `https://wd5-impl-services1.workday.com/ccx/oauth2/<your_tenant>/token` 

*Reference the URls Workday provides once you create the API Client in Workday. They will provide the specific URLs needed based on the tenant and data center.*

**Steps to Set Up OAuth**:

1. Use the Register API client task in Workday.
2. Set your API client settings in workday similar to the provided example below.  
3. Scopes will vary depending on the actions being performed by GPT. For this use-case, you will need: `Staffing`, `Tenant Non-Configurable`, `Time Off and Leave`, `Include Workday Owned Scope`
4. Enter the **Redirection URI** from the GPT into the API client settings.
5. Store the **Client ID** and **Client Secret** for later use in GPT.  
6. Add the OAuth details into the GPT Authentication section as shown below.  

*The redirection URI is retrieved from the GPT setup once OAuth has been selected as authentication, on the GPT set-up screen.* 

![workday-cgpt-oauth.png](../../../../images/workday-cgpt-oauth.png)

![workday-api-client.png](../../../../images/workday-api-client.png)

The [Workday Community page on API client]((https://doc.workday.com/admin-guide/en-us/authentication-and-security/authentication/oauth/dan1370797831010.html)) can be a good resource to go deeper *(this requires a community account)*.

## Sample Use Case: PTO Submission and Benefit Plan Inquiry

### Overview

This use case demonstrates how to help employees submit PTO requests, retrieve worker details, and view benefit plans through a RAAS report.

## GPT Instructions

Use the following instructions to cover PTO Submission use-cases, Worker details retrieval and benefit plan inquiry:

```
# **Context:** You support employees by providing detailed information about their PTO submissions, worker details, and benefit plans through the Workday system. You help them submit PTO requests, retrieve personal and job-related information, and view their benefit plans. Assume the employees are familiar with basic HR terminologies.
# **Instructions:**
## Scenarios
### - When the user asks to submit a PTO request, follow this 3 step process:
1. Ask the user for PTO details, including start date, end date, and type of leave.
2. Submit the request using the `Request_Time_Off` API call.
3. Provide a summary of the submitted PTO request, including any information on approvals.

### - When the user asks to retrieve worker details, follow this 2 step process:
1. Retrieve the worker’s details using `Get_Workers`.
2. Summarize the employee’s job title, department, and contact details for easy reference.

### - When the user asks to inquire about benefit plans, follow this 2 step process:
1. Retrieve benefit plan details using `Get_Report_As_A_Service`.
2. Present a summary of the benefits.
```

### Creating request on behalf of the employee

As employee ID is required to take actions on Workday onto the employee, this information will need to be retrieved before doing any queries. We have accomplished this by calling a RAAS report in workday after authentication that provides the user who is logging in. There may be another way to do this via just a REST API call itself. Once the ID has been returned it will be used in all other actions.

Sample RAAS Report: Using the field Current User will return the worker who has authenticated via OAuth.    
![custom-report-workday-01.png](../../../../images/custom-report-workday-01.png)

![custom-report-workday-02.png](../../../../images/custom-report-workday-02.png)

### OpenAPI Schema

Below is an example OpenAPI schema generated using the Workday REST API Reference and [ActionsGPT](https://chatgpt.com/g/g-TYEliDU6A-actionsgpt).

We're using the following API calls:
* **\[POST\] Request\_Time\_Off**: Creates a time off request for an employee.  
* **\[GET\] Get\_Workers**: Retrieves information on worker details.  
* **\[GET\] Get\_eligibleAbsenceTypes**: Retrieves eligible time off plans.  
* **\[GET\] Get\_Report\_As\_A\_Service (RAAS)**: Pulls reports, including custom RAAS reports, for benefit details.


Replace the paths with the correct tenant ID and configure them to the appropriate servers. Ensure the required IDs are set correctly for different PTO types.

```yaml
openapi: 3.1.0
info:
  title: Workday Employee API
  description: API to manage worker details, absence types, and benefit plans in Workday.
  version: 1.3.0
servers:
  - url: https://wd5-impl-services1.workday.com/ccx
    description: Workday Absence Management API Server
paths:
  /service/customreport2/tenant/GPT_RAAS:
    get:
      operationId: getAuthenticatedUserIdRaaS
      summary: Retrieve the Employee ID for the authenticated user.
      description: Fetches the Employee ID for the authenticated user from Workday.
      responses:
        '200':
          description: A JSON object containing the authenticated user's Employee ID.
          content:
            application/json:
              schema:
                type: object
                properties:
                  employeeId:
                    type: string
                    description: The Employee ID of the authenticated user.
                    example: "5050"
        '401':
          description: Unauthorized - Invalid or missing Bearer token.
      security:
        - bearerAuth: []

  /api/absenceManagement/v1/tenant/workers/Employee_ID={employeeId}/eligibleAbsenceTypes:
    get:
      operationId: getEligibleAbsenceTypes
      summary: Retrieve eligible absence types by Employee ID.
      description: Fetches a list of eligible absence types for a worker by their Employee ID, with a fixed category filter.
      parameters:
        - name: employeeId
          in: path
          required: true
          description: The Employee ID of the worker (passed as `Employee_ID=3050` in the URL).
          schema:
            type: string
            example: "5050"
        - name: category
          in: query
          required: true
          description: Fixed category filter for the request. This cannot be changed.
          schema:
            type: string
            example: "17bd6531c90c100016d4b06f2b8a07ce"
      responses:
        '200':
          description: A JSON array of eligible absence types.
          content:
            application/json:
              schema:
                type: object
                properties:
                  absenceTypes:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                        name:
                          type: string
        '401':
          description: Unauthorized - Invalid or missing Bearer token.
        '404':
          description: Worker or absence types not found.
      security:
        - bearerAuth: []

  /api/absenceManagement/v1/tenant/workers/Employee_ID={employeeId}:
    get:
      operationId: getWorkerById
      summary: Retrieve worker details by Employee ID.
      description: Fetches detailed information of a worker using their Employee ID.
      parameters:
        - name: employeeId
          in: path
          required: true
          description: The Employee ID of the worker.
          schema:
            type: string
            example: "5050"
      responses:
        '200':
          description: A JSON object containing worker details.
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: object
                    properties:
                      firstName:
                        type: string
                      lastName:
                        type: string
                  position:
                    type: string
                  email:
                    type: string
        '401':
          description: Unauthorized - Invalid or missing Bearer token.
        '404':
          description: Worker not found.
      security:
        - bearerAuth: []

  /api/absenceManagement/v1/tenant/workers/Employee_ID={employeeId}/requestTimeOff:
    post:
      operationId: requestTimeOff
      summary: Request time off for a worker.
      description: Allows a worker to request time off by providing the necessary details.
      parameters:
        - name: employeeId
          in: path
          required: true
          description: The Employee ID of the worker requesting time off.
          schema:
            type: string
            example: "5050"
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                days:
                  type: array
                  description: Array of days for which the time off is being requested.
                  items:
                    type: object
                    properties:
                      start:
                        type: string
                        format: date
                        description: The start date of the time off.
                        example: "2024-11-26"
                      date:
                        type: string
                        format: date
                        description: The specific date for the time off.
                        example: "2024-11-26"
                      end:
                        type: string
                        format: date
                        description: The end date of the time off.
                        example: "2024-11-26"
                      dailyQuantity:
                        type: number
                        description: The number of hours per day to take off.
                        example: 8
                      timeOffType:
                        type: object
                        description: Time off type with corresponding ID.
                        properties:
                          id:
                            type: string
                            description: The ID of the time off type.
                            example: "b35340ce4321102030f8b5a848bc0000"
                            enum:
                              - <flexible_time_off_id_from_workday>  # Flexible Time Off ID (hexa format)
                              - <sick_leave_id_from_workday>  # Sick Leave ID (hexa format)
      responses:
        '200':
          description: Time off request created successfully.
        '400':
          description: Invalid input or missing parameters.
        '401':
          description: Unauthorized - Invalid or missing Bearer token.
        '404':
          description: Worker not found.
      security:
        - bearerAuth: []

  /service/customreport2/tenant/GPT_Worker_Benefit_Data:
    get:
      operationId: getWorkerBenefitPlans
      summary: Retrieve worker benefit plans enrolled by Employee ID.
      description: Fetches the benefit plans in which the worker is enrolled using their Employee ID.
      parameters:
        - name: Worker!Employee_ID
          in: query
          required: true
          description: The Employee ID of the worker.
          schema:
            type: string
            example: "5020"
        - name: format
          in: query
          required: true
          description: The format of the response (e.g., `json`).
          schema:
            type: string
            example: "json"
      responses:
        '200':
          description: A JSON array of the worker's enrolled benefit plans.
          content:
            application/json:
              schema:
                type: object
                properties:
                  benefitPlans:
                    type: array
                    items:
                      type: object
                      properties:
                        planName:
                          type: string
                        coverage:
                          type: string
                        startDate:
                          type: string
                          format: date
                        endDate:
                          type: string
                          format: date
        '401':
          description: Unauthorized - Invalid or missing Bearer token.
        '404':
          description: Worker or benefit plans not found.
      security:
        - bearerAuth: []

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    worker:
      type: object
      properties:
        id:
          type: string
        name:
          type: object
          properties:
            firstName:
              type: string
            lastName:
              type: string
        position:
          type: string
        email:
          type: string
    absenceTypes:
      type: array
      items:
        type: object
        properties:
          id:
            type: string
          name:
            type: string
    benefitPlans:
      type: array
      items:
        type: object
        properties:
          planName:
            type: string
          coverage:
            type: string
          startDate:
            type: string
            format: date
          endDate:
            type: string
            format: date
    timeOffTypes:
      type: object
      description: Mapping of human-readable time off types to their corresponding IDs.
      properties:
        Flexible Time Off:
          type: string
          example: "b35340ce4321102030f8b5a848bc0000"
        Sick Leave:
          type: string
          example: "21bd0afbfbf21011e6ccc4dc170e0000"


```

## Conclusion

Congratulations on setting up a GPT for Workday with capabilities such as PTO submission, employee details retrieval, and benefits plan inquiry!

This integration can streamline HR processes, provide quick access to personal details, and make it easy for employees to request PTO. This guide provides a customizable framework for implementing ChatGPT with Workday, allowing you to easily add more actions and enhance GPT capabilities further.

![workday-gpt.png](../../../../images/workday-gpt.png)

![pto-request.png](../../../../images/pto-request.png)
