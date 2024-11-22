# GPT Action Library: Google Calendar

## Introduction

This page provides an instruction & guide for developers building a GPT Action for a specific application. Before you proceed, make sure to first familiarize yourself with the following information: 

- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

This GPT Action provides an overview of how to connect to your **Google Calendar**. It uses OAuth to link to your Google account, enabling you to create, read, update, and delete events within your calendar.

### Value + Example Business Use Cases

**Value**: Users can now leverage ChatGPT's natural language capability to connect directly to their Google Calendar.

**Example Use Cases**: 
- You want to create a new event in your calendar. 
- You want to search your calendar for events based on a specific criteria. 
- You want to delete an event from your calendar. 

***Note:*** This is a good example of an GPT that may be useful to call from other GPTs using the @<name of your GPT> function. You can find more information on this feature on our [help site](https://help.openai.com/en/articles/8908924-what-is-the-mentions-feature-for-gpts). 


## Application Information

### Application Prerequisites

Before you get started, ensure you can meet the following pre-requistes.

 - A Google account with Google Calendar access. 
 - Permissions to access the Google Calendar API and use the Google Cloud Console to configure your OAuth credentials. 

# Google Calendar Configuration Steps

## Enabling the Google Calendar API

- Visit [console.cloud.google.com](https://console.cloud.google.com).
- In the project selector, choose the project you’d like to use for this GPT Action. If you don’t have a project yet, click the **Create Project** button.
- When creating a new project, enter a name for it and select the billing account you’d like to associate. In this example, ‘No Organization’ is selected.

<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(55.43981481481482% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/0QxHM3NKyUZcv3di9CkA?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="Cookbook | Create Google Cloud Project" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

You now have a Google Cloud Project and are ready to configure the API access to your Google Calendar.

- In the Quck Access menu, select **APIs & Services** > **Library**
- Search for **Google Calendar API** (not DKIM) and click on it.
- Click on the **Enable** button.

<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(53.793774319066145% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/uEOZVBdf8OZ8sP0DZAld?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="Cookbook | Enable Google Calendar API" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

## Creating up OAuth Credentials

The next step is to configure the OAuth credentials to allow your GPT Action to access your Google Calendar.

Depending on your current configuration you may need to configure your OAuth consent screen. We'll start with that. 

- In the left menu click **Credentials**
- Now click **Configure consent screen**
- If you get the option, choose **Go To New Experience** and click **Get Started**
- Enter your app name and choose your email in the User support email dropdown.
- Choose Internal audience and enter a contact email. 
- Agree to the terms and click **Create** 


<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(53.793774319066145% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/Xs5oyXa1ssYY9zyPsL0s?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="Cookbook | Create Consent Screen" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

We are now ready to create the OAuth credentials. 

- Click **Create OAuth Credentials**
- Choose **Web Application**
- Enter your application name
- Under Authorizes JavaScript Origins, enter `https://chat.openai.com` & `https://chatgpt.com`
- For now we'll leave the **Authorized redirect URIs** blank. (we'll come back to this later)
- Click **Create**
- Open the credentials page and you'll see your OAuth client ID and client secret on the right of the screen.


<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(53.793774319066145% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/OHyS6C3ETFPCc4eqrQ4a?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="OAuth overview – Google Auth Platform – cookbook-demo – Google Cloud console" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

## Configuring OAuth Scopes

Next, configure the scopes (or services) that the OAuth client ID will have access to. In this case, we’ll configure access to the Google Calendar API.

- In the left menu click **Data Access**
- Click **Add or Remove Scopes**
- In the right panel filter on `https://www.googleapis.com/auth/calendar`
- In the filtered results, choose the first result, the scope should end with `/auth/calendar`
- Click **Update** and then **Save**


<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(53.793774319066145% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/mbsRtOs10arPZtzjeum2?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="Clients – Google Auth Platform – cookbook-demo – Google Cloud console" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

# GPT Action Configuration Steps

We are now ready to configure the GPT Action. First we'll configure the OAuth settings to allow the GPT to authenticate with Google Calendar. 

- In your GPT, create an action. 
- Click on the settings gear icon and select **OAuth**
- Enter the **Client ID** and **Client Secret** from the Google Cloud Console. 
- Enter the following details: 
  - Authorization URL: `https://accounts.google.com/o/oauth2/auth`
  - Token URL: `https://oauth2.googleapis.com/token`
  - Scopes: `https://www.googleapis.com/auth/calendar`
- Leave the Token Exchange Method as default. 
- Click **Save**


<img src="../../../images/google-calendar-action-config.png" alt="Google Calendar OAuth" width="400"/>

We can now enter the OpenAPI schema for the action. The config below allows reading and creating events. Enter this in the OpenAPI schema field.

```yaml
openapi: 3.1.0
info:
  title: Google Calendar API
  description: This API allows you to read and create events in a user's Google Calendar.
  version: 1.0.0
servers:
  - url: https://www.googleapis.com/calendar/v3
    description: Google Calendar API server

paths:
  /calendars/primary/events:
    get:
      summary: List events from the primary calendar
      description: Retrieve a list of events from the user's primary Google Calendar.
      operationId: listEvents
      tags:
        - Calendar
      parameters:
        - name: timeMin
          in: query
          description: The lower bound (inclusive) of the events to retrieve, in RFC3339 format.
          required: false
          schema:
            type: string
            format: date-time
            example: "2024-11-01T00:00:00Z"
        - name: timeMax
          in: query
          description: The upper bound (exclusive) of the events to retrieve, in RFC3339 format.
          required: false
          schema:
            type: string
            format: date-time
            example: "2024-12-01T00:00:00Z"
        - name: maxResults
          in: query
          description: The maximum number of events to return.
          required: false
          schema:
            type: integer
            default: 10
        - name: singleEvents
          in: query
          description: Whether to expand recurring events into instances. Defaults to `false`.
          required: false
          schema:
            type: boolean
            default: true
        - name: orderBy
          in: query
          description: The order of events. Can be "startTime" or "updated".
          required: false
          schema:
            type: string
            enum:
              - startTime
              - updated
            default: startTime
      responses:
        '200':
          description: A list of events
          content:
            application/json:
              schema:
                type: object
                properties:
                  items:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          description: The event ID
                        summary:
                          type: string
                          description: The event summary (title)
                        start:
                          type: object
                          properties:
                            dateTime:
                              type: string
                              format: date-time
                              description: The start time of the event
                            date:
                              type: string
                              format: date
                              description: The start date of the all-day event
                        end:
                          type: object
                          properties:
                            dateTime:
                              type: string
                              format: date-time
                              description: The end time of the event
                            date:
                              type: string
                              format: date
                              description: The end date of the all-day event
                        location:
                          type: string
                          description: The location of the event
                        description:
                          type: string
                          description: A description of the event
        '401':
          description: Unauthorized access due to missing or invalid OAuth token
        '400':
          description: Bad request, invalid parameters

    post:
      summary: Create a new event on the primary calendar
      description: Creates a new event on the user's primary Google Calendar.
      operationId: createEvent
      tags:
        - Calendar
      requestBody:
        description: The event data to create.
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                summary:
                  type: string
                  description: The title of the event
                  example: "Team Meeting"
                location:
                  type: string
                  description: The location of the event
                  example: "Conference Room 1"
                description:
                  type: string
                  description: A detailed description of the event
                  example: "Discuss quarterly results"
                start:
                  type: object
                  properties:
                    dateTime:
                      type: string
                      format: date-time
                      description: Start time of the event
                      example: "2024-11-30T09:00:00Z"
                    timeZone:
                      type: string
                      description: Time zone of the event start
                      example: "UTC"
                end:
                  type: object
                  properties:
                    dateTime:
                      type: string
                      format: date-time
                      description: End time of the event
                      example: "2024-11-30T10:00:00Z"
                    timeZone:
                      type: string
                      description: Time zone of the event end
                      example: "UTC"
                attendees:
                  type: array
                  items:
                    type: object
                    properties:
                      email:
                        type: string
                        description: The email address of an attendee
                        example: "attendee@example.com"
              required:
                - summary
                - start
                - end
      responses:
        '201':
          description: Event created successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                    description: The ID of the created event
                  summary:
                    type: string
                    description: The event summary (title)
                  start:
                    type: object
                    properties:
                      dateTime:
                        type: string
                        format: date-time
                        description: The start time of the event
                  end:
                    type: object
                    properties:
                      dateTime:
                        type: string
                        format: date-time
                        description: The end time of the event
        '400':
          description: Bad request, invalid event data
        '401':
          description: Unauthorized access due to missing or invalid OAuth token
        '500':
          description: Internal server error
```

If successful, you'll see the two endpoints appear at the bottom of the configuration screen.

<img src="../../../images/google-calendar-action-endpoints.png" alt="Google Calendar Action Endpoints" width="600"/>

# Setting callback URL

Now that we've configured the OAuth settings and set the OpenAPI schema, ChatGPT will generate a callback URL. You’ll need to add this URL to the **Authorized redirect URIs** in the Google Cloud Console.

Exit the action configuration screen in ChatGPT and scroll to the bottom. There, you'll find the generated callback URL.

**Note:** If you modify the OAuth settings, a new callback URL will be generated, which will also need to be added to the **Authorized redirect URIs** in the Google Cloud Console."

<img src="../../../images/google-calendar-callback.png" alt="Google Calendar Callback URL" width="600"/>

Copy this URL and add it to the **Authorized redirect URIs** in the Google Cloud Console, then click **Save**.

<img src="../../../images/google-calendar-callback-settings.png" alt="Google Calendar Callback URL" width="600"/>


# Testing the Action

With your action configured, you can now test it in ChatGPT. Start by asking your GPT a test question, for example: `What events do I have today?` If this is the first time you've used the action, you'll be prompted to authorize the action. Click **Sign in with googleapis.com** and follow the prompts to authorize the action. 

<img src="../../../images/google-signin.png" alt="Google Calendar Sign In" width="600"/>

Once authorized, you should then see the results from your calendar. 

<img src="../../../images/google-calendar-results.png" alt="Google Calendar results" width="600"/>

