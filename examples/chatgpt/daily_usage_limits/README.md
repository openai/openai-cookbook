# Release ChatGPT usage budgets hourly, daily, or weekly

This runnable example automates ChatGPT Enterprise and Edu usage-limit updates with the [ChatGPT Admin API](https://chatgpt.com/public/admin/api-reference). It includes a Node.js program you can try locally, then configure for your workspace.

Usage limits in **ChatGPT Enterprise and Edu are monthly**. A user who spends their allocation in the first week reaches the limit with most of the month still ahead.

Release portions of a budget in **credits or US dollars (USD)** hourly, daily, weekly, or on a custom schedule to keep capacity available for later work. Choose amounts and schedules for individual users, a department, or your workspace.

For your most active users, increase the available amount based on recent consumption, up to a monthly maximum you set. Pair these adjustments with regular usage updates so people understand what remains, when more will be available, and how their model choices affect consumption.

## Keep capacity available throughout the month

The illustration uses **2,000 credits per person per month**. All amounts in this guide are examples; choose budgets that fit the people and teams you support.

![A person uses a 2,000-credit monthly budget in the first week and has no credits left for the remaining weeks.](assets/monthly-budget-problem.svg)

Releasing 500 credits each week reserves part of that allocation for later weeks. Each release increases the person's monthly limit, reaching the full 2,000 credits with the fourth release.

<details>
<summary>Monthly reset dates</summary>

Usage limits reset on the first day of each month in UTC by default. A workspace can also align its monthly usage period with its billing cycle. [See your workspace's usage period](https://help.openai.com/en/articles/20001001-manage-usage-limits-and-overages-in-chatgpt-enterprise-and-edu).

</details>

## Try a release plan in your browser

Open the [interactive example](assets/release-explorer.html). Choose **Credits**, **US dollars (USD)**, or **Both** to compare two separate example plans. Change the budgets and release schedules, and see how usage affects the amount available.

| Release date | New credits available | Monthly limit after release |
| --- | ---: | ---: |
| Day 1 | 500 | 500 |
| Day 8 | 500 | 1,000 |
| Day 15 | 500 | 1,500 |
| Day 22 | 500 | 2,000 |

![Four releases of 500 credits increase the monthly limit to 2,000.](assets/release-timeline.svg)

Unused released credits remain available within the month. You choose the total monthly budget and when each portion becomes available.

## Choose dollars or credits

Use the billing unit shown in your workspace's usage settings for your customer agreement. Choose **Credits** for a credit-based workspace or **US dollars (USD)** for a workspace with dollar-denominated usage and limits. The controller checks the API's reported unit before applying a plan.

| Example plan | Monthly budget per person | Weekly release | Configuration |
| --- | ---: | ---: | --- |
| Credits | 2,000 credits | 500 credits | `"unit": "credit"` |
| US dollars | $200.00 | $50.00 | `"unit": "usd"` |

These are separate illustrative budgets. Choose amounts for your organization in its billing unit. Credit limits use whole credits; dollar limits use cents. All three release approaches support both units. [Configure the unit and amounts](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#choose-the-billing-unit).

## Get started

You need **Node.js 24 or later** to run the local example on **Windows, macOS, or Linux**. It uses three fictional people and keeps all changes in memory. You do not need an Admin API key.

1. [Download the starter ZIP](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/chatgpt/daily_usage_limits/assets/chatgpt-usage-budget-starter.zip) and extract it.
2. Open the `chatgpt-usage-budget-starter` folder. It contains `README.md`, `docs`, `src`, and `assets`.
3. Open a terminal in that folder. On Windows, right-click the folder's background in File Explorer and choose **Open in Terminal**. On macOS or Linux, open Terminal, type `cd `, drag the extracted folder into the window, and press Enter.

Run the credit example:

```bash
node src/demo.mjs --unit credit
```

Or run the dollar example:

```bash
node src/demo.mjs --unit usd
```

The program previews the first release, applies it in the local simulator, and advances to the next weekly release. Each fictional person's limits follow the selected plan:

| Example | Starting monthly limit | First release | Next weekly release |
| --- | ---: | ---: | ---: |
| Credits | 2,000 credits | 500 credits | 1,000 credits |
| US dollars | $200.00 | $50.00 | $100.00 |

The demonstration also simulates an interrupted update and a conflicting admin edit, then restores the starting settings. A successful run ends with `Demo complete. All simulated state stayed in memory.`

Choose the setup path that fits the tools available to you:

| Your setup | Guide |
| --- | --- |
| You use Codex and want help with setup. | [Open the folder in Codex](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/get-started.md#let-codex-help) and ask it to run the example. |
| Your team provides a managed computer, virtual machine, or cloud environment. | [Run in that environment](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/get-started.md#use-a-managed-environment). This path also works when you cannot run the required software on your computer. |

After the demonstration, choose the people, amounts, and schedule for your pilot.

## How the weekly plan uses the API

This configuration excerpt expresses the 500-credit weekly plan. Include these fields in the complete configuration created by the [configuration and enrollment guide](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#prepare-a-reviewed-enrollment), and replace the example `anchor` with the start of your plan within the confirmed monthly period.

```json
{
  "unit": "credit",
  "policy": {
    "pattern": "fixed_release",
    "anchor": "2030-01-01T00:00:00Z",
    "intervalHours": 168,
    "startCap": "500",
    "increment": "500",
    "ceiling": "2000"
  }
}
```

`startCap` sets the first monthly limit. Every 168 hours, the controller adds `increment` to the scheduled target, up to `ceiling`. The resulting monthly limits are **500, 1,000, 1,500, and 2,000 credits**. A repeated run in the same week keeps the same target; a missed run catches up to the current week's target.

For the second release, the [API adapter](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/src/admin-api.mjs) sends a request with this shape after the enrollment and proposed changes have been reviewed. `WORKSPACE_ID` and `USER_ID` below stand for the selected workspace and enrolled person:

```http
PATCH /v1/manage/workspaces/WORKSPACE_ID/usage_limits/users/USER_ID
Host: api.chatgpt.com
Content-Type: application/json

{
  "override_monthly_usage_limit": {
    "type": "limited",
    "limit_amount": { "unit": "credit", "amount": "1000" },
    "temporary": true
  }
}
```

The request sets that person's total monthly limit to 1,000 credits. The workspace balance and monthly usage period stay unchanged. `temporary: true` makes the override expire at the end of that period. Continue with the [reviewed enrollment and preview steps](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#prepare-a-reviewed-enrollment) before applying a plan to your workspace; the [API contract](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/api-contract.md) covers authentication, units, and restoration.

## Choose how to release the budget

| Approach | Use it to |
| --- | --- |
| Scheduled releases | Spread a monthly allocation across hourly, daily, weekly, or custom releases. |
| Usage-based increases | Give active users more capacity as consumption grows, up to a monthly maximum. |

Set different budgets and schedules for different populations. For example, give a project team weekly releases and use consumption-based increases for a small group of power users. Keep each person in one active configuration.

See [policy configuration and examples](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#choose-a-policy) for the settings. Share the monthly allocation, usage so far, and next release date through your existing communication channels. Use those updates to help people choose models that fit their work and available budget.

## Test with a small group

Use a local run or Codex automation to try the approach with a small group. Review the proposed limits, observe how the release schedule fits their work, and adjust the plan.

For ongoing workspace budget management, run the program on **organization-managed infrastructure**, such as a managed virtual machine or cloud service. Assign a team to monitor it and keep it running independently of an individual's computer.

![Test locally or with Codex, then run ongoing releases on organization-managed infrastructure.](assets/control-flow.svg)

| Next step | Guide |
| --- | --- |
| Test a scheduled Codex pilot | [Set up a Codex pilot](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/codex.md) |
| Run on a managed macOS or Linux computer or server | [Set up a managed host](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/local.md) |
| Deploy using your AWS account | [Deploy on AWS](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/aws.md) |

The AWS guide includes a deployment template, queued processing for larger enrollments, and progress tracking. Start with a small group, then increase the enrollment as you verify completion and API throughput. Your technical team can adapt the program to other infrastructure your organization operates.

For Windows admins, the AWS guide provides a browser-based setup path through AWS CloudShell. Live local scheduling uses the included macOS or Linux service setup.

## Prepare a reviewed enrollment

Choose a workspace, then select people by user ID, email address, workspace group ID, or all current members. Review the resolved list, current settings, monthly period, and proposed changes. The [configuration and enrollment guide](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#prepare-a-reviewed-enrollment) takes you through each step. A preview shows the proposed limits before you apply them.

## Stop, restore, and renew

The program saves the original settings and records its changes. Follow the [stop and restore procedure](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#stop-restore-and-renew) when ending a pilot or changing its policy. For the next monthly period on AWS, [confirm its dates and review the opening limits](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/aws.md#7-renew-the-next-period). The renewal helper carries forward your policy and people on the same deployment, with its existing records and credentials.

For implementation details, see the [verification guide](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/verification.md) and [API contract](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/api-contract.md).
