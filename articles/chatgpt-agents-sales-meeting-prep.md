# Building workspace agents in ChatGPT to complete repeatable, end-to-end work

This cookbook shows how to build a ChatGPT workspace agent. Currently available in research preview for ChatGPT Business, Enterprise, and Edu customers, workspace agents are evolutions of GPTs that can work across tools to complete high-value tasks, helping your team move faster.

In this cookbook, we'll create a workspace agent through the conversational builder, give it access to our team's calendars and knowledge bases, and add a brief-writing skill to help craft the agent's output. Then we'll test our team agent, schedule it to run on a recurring schedule, and share it with teammates.

## Introduction

ChatGPT workspace agents are shared agents that can run repeatable workflows across ChatGPT and independently complete end-to-end tasks. They can use connected apps, follow skills, run on a schedule, and they can be shared with your colleagues in your workspace.

In this cookbook, we'll build a workspace agent that supports a sales team. Sales teams often spend time manually pulling account notes, recent customer feedback, product usage metrics, and company news to prepare for upcoming customer meetings.

We'll build a workspace agent that helps our sales team more efficiently prepare for their sales meetings by automatically generating meeting briefs ahead of upcoming customer calls, backed by up-to-date customer data. Specifically, our agent will run each day to check tomorrow's customer meetings, gather recent account context from SharePoint, and search the web for recent company news and background information on each attendee. Our agent will generate a meeting brief, save it down as a SharePoint doc, and send us an executive summary.

Once our agent is deployed, it will run automatically each day, and we can also invoke it on-demand in ChatGPT.

## Prerequisites and setup

For this cookbook, you will need a ChatGPT Business, Enterprise, or Edu workspace with access to workspace agents. Our agent will read upcoming meetings from Google Calendar, save meeting briefs in Microsoft SharePoint, and email a summary through Gmail.

Before you build, confirm these three settings with your workspace admin.

1. **Agents are enabled for your workspace.** Workspace owners can enable agents for the workspace and assign access to specific roles with RBAC.
2. **You have permission to build and share agents.** An admin will need to enable you (or the appropriate RBAC group) to create agents. If you plan to share the agent, an admin may also need to enable publishing.
3. **The apps you need are enabled.** For this cookbook, an admin would need to enable Google Calendar, Gmail, and SharePoint in workspace app settings.

If you want to run a version of this agent from Slack, follow the [Workspace Agents in Slack setup instructions](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business). A Slack deployment requires shared authentication for every app connection. This example runs in ChatGPT so each teammate can use their own calendar and email account.

## Building your agent

The conversational agent builder is the fastest way to start. It can draft the agent profile, choose apps, generate a skill, write instructions, and prepare a draft agent that you can test in Preview. We'll use that flow here, then review each piece step by step so you can refine the agent later.

Note that if you want inspiration on work to automate, you can start from pre-built agent templates including a Chief of Staff, Data Analysis, and Customer Support agents.

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img0.png" alt="Build a new agent" width="80%" />
</p>

### 1. Describe your workflow

We'll enter the following text into the agent builder:

```text
Create an agent to help with sales meeting prep. The agent should check my Google Calendar for tomorrow's customer meetings. Exclude internal-only meetings and skip events with no external attendees.

For each customer meeting, pull recent notes and feedback from SharePoint, then search the web for any relevant company news from the last 30 days. Then write a 2-3 page meeting brief. Save the meeting brief as a SharePoint doc.

Then, send me an email with a daily summary of my upcoming meetings, with a link to the full brief.
```

You'll see the assistant create a plan for building the agent, then starting to build each component step-by-step. The first draft should give you a working agent with a name, description, instructions, and a set of connected apps.

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img1-v2.png" alt="Agent builder in progress" width="80%" />
</p>

If you don't have the required apps already configured, the agent builder will walk you through the configuration steps. If Gmail is unavailable, you can ask the agent to return the link to the SharePoint brief in ChatGPT.

### 2. Review and configure your apps

Now we'll review the configurations of our apps. Because our agent can access external tools, it's important to understand the permissions it has to take actions on these tools, and how those permissions change as we share our agent for other teammates to use.

Workspace admins control which app actions are available. For this example, the SharePoint app needs permission to search for customer documents and create meeting briefs. If your workspace limits SharePoint to read-only actions, have the agent return the brief in ChatGPT.

We can click into each app to view and change its permissions.

For the **Google Calendar** connection, we'll use *End-user account*. Each person who runs the agent in ChatGPT connects their own Google Calendar account so the agent can read their meetings.

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img2.png" alt="End-user auth for Google Calendar" width="60%" />
</p>

For Google Calendar, we just need to view upcoming meetings and attendees, so we'll only enable read actions. We can also enforce permissions more granularly, by selecting individual actions to enable or disable.

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img3.png" alt="Read access for Google Calendar" width="60%" />
</p>

We'll also use the same *End-user account* configuration for the **Gmail** app, since each agent user will get their own email briefing for their upcoming meetings.

For the **Microsoft SharePoint** connection, we'll use an *Agent-owned account* linked to a sales team service account. Give that account access to the customer documents the agent needs and the folder where it will save briefs. The agent uses that same account for every run.

In this case, we want to be able to search through SharePoint for any documents relevant to a customer account, then create a new meeting prep document. So we'll scope the SharePoint app permissions accordingly, to allow a broad set of read actions but prevent bulk write actions and prevent deletes.

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img4.png" alt="Scoped permissions for SharePoint" width="60%" />
</p>

Alongside these apps, the agent uses **Web search** to find public company news from the last 30 days.

### 3. Enabling skills and memories for consistent, customized outputs

One of the benefits of using workspace agents is how easy it is to ensure **high-quality and consistent** outputs, and skills are an ideal way to help our agent follow the same workflow each time it generates a meeting prep document.

Skills package instructions, resources, and scripts to help our agent reliably complete its instructions. To equip our agent with a skill, we'll select "Add skill" in our agent view. We can upload a skill that we've already created (skills are built on the [open-source agent skills standard](https://agentskills.io/home) so you can use them across AI products), or we can use the built-in skill builder directly within ChatGPT workspace agents.

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img5.png" alt="Creating a skill for our agent" width="336" />
</p>

Our assistant will read the meeting template and help us create a custom skill that matches the output format we want. To refine the skill, edit it directly in the agent builder or upload files it can use.

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img6.png" alt="Editing a skill for our agent" width="60%" />
</p>

We'll also enable **Memory** for our agent. Memory enables the agent to maintain context across different agent sessions, by giving it access to a persistent folder where the agent can save notes, drafts, and outputs. In this case, we'll give the agent memory for previous runs of this agent so it knows per-user context.

Note that this memory is not shared across different end users of our agent. Users can view their memories from the agent page. For example, a user might give the agent guidance to ignore a certain meeting on its calendar that it doesn't need a meeting prep doc for, and the agent will be able to access that memory when following its instructions.

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img7.png" alt="Giving our agent access to memory" width="60%" />
</p>

## Testing your agent

Before scheduling our agent to run on a periodic cadence, and before sharing it with other teammates, we can select **Preview** or **Try in ChatGPT** in the top-right corner of the agent builder to test our agent. We can also select **Create** to save our agent, and then invoke it by tagging it in our ChatGPT input box. Note that when you first create an agent, it is by default available only to you.

Note that our agent builder has automatically created some sample starter prompts that appear next to the agent in ChatGPT. To view and edit these prompts, we can select ChatGPT under "Channels" in the agent view.

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img9.png" alt="Updating starter prompts" width="336" />
</p>

We'll ask our agent to prepare briefs for tomorrow's meetings. In the run, we can review the app actions it takes, such as reading calendar events and creating a SharePoint document.

When our agent completes, we see that it has generated polished SharePoint documents for each of our upcoming customer meetings and sent us an email summary.

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img11.png" alt="Output email" width="80%" />
</p>

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img12.png" alt="Output meeting brief" width="80%" />
</p>

You can run additional tests with different input data - for example, you might ask the agent to prepare a brief for a meeting that you already had last week, to compare its output with a human-generated prep doc. You can also add that prep doc to the skill's files as an example. You can update the agent's instructions, configure its apps and permissions, or update its skill to refine the output it produces.

## Deploying your agent

We'll first set our agent to run each day at 4pm, to give us a preview of the upcoming day. We'll select **Schedule** in the top-right of the agent screen and then **Add new schedule** to specify when the agent should run, and provide it any specific instructions.

For example, in addition to our daily weekday schedule, we might want to create a "weekly prep" schedule that runs each Sunday evening, and instruct our agent to prepare meeting briefs for each upcoming meeting this week.

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img10.png" alt="Creating a schedule" width="336" />
</p>

To share the agent, open it in the builder and select **Share**. Your workspace admin controls whether you can share agents.

Invite sales teammates with **Can chat** so they can run the agent. To let a teammate maintain it with you, grant **Can edit**. Editors can update the shared draft and publish new versions. A teammate who wants a separate version can duplicate the agent. See the [workspace agent sharing guide](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business).

Each teammate runs the agent with their own Google Calendar and Gmail connections. **Anyone who can run the agent can also use its enabled SharePoint actions through the sales team service account.** Before sharing, check which content the service account can access and which SharePoint actions the agent can take.

In addition to providing our teammates with a link to our agent, we can also choose to list our agent in our company directory, allowing anyone in your workspace to view the agent. You can access your company directory of employee-built agents by selecting **Agents** from ChatGPT, and then selecting the agent directory tab.
