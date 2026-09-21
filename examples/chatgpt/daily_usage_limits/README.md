# Release ChatGPT usage budgets hourly, daily, or weekly

Usage limits in **ChatGPT Enterprise and Edu are monthly**. By default, they reset on the first day of each month in UTC. See [how monthly usage limits work](https://help.openai.com/en/articles/20001001-manage-usage-limits-and-overages-in-chatgpt-enterprise-and-edu). The [usage-limits endpoints in the ChatGPT Admin API](https://chatgpt.com/public/admin/api-reference) let you update those limits throughout the month.

This example uses that API to make a monthly budget available in **hourly, daily, weekly, or custom increments**. Choose the amount, schedule, and people included: a few power users, a department, or a reviewed workspace roster. The controller—the program that applies the schedule—increases each person's cumulative monthly limit as more budget becomes available.

## The problem: a monthly limit can run out early

A monthly limit sets a boundary, but a busy user can reach it well before the month ends. That can leave them without capacity for the work still ahead.

Releasing budget more frequently helps spread access across the month. It also gives admins regular opportunities to review consumption and tell people what is available now and when more will be released. For your most active users, you can instead adjust headroom based on recent usage while keeping a monthly maximum you choose.

**The 2,000-credit monthly budget below is an illustration, not an OpenAI default or recommendation.** Use the amounts that fit your organization and each population you support.

![Illustrative example: a person uses a 2,000-credit monthly budget in the first week and has no capacity left for the remaining weeks.](assets/monthly-budget-problem.svg)

## Try a release plan in your browser

Open the [interactive example](assets/release-explorer.html). Change the monthly budget, compare release schedules, and see how usage affects the amount available. It runs in your browser with fictional numbers; no installation or credentials are needed.

For illustration, a **2,000-credit monthly budget** could become available in four weekly portions:

| Release date | New credits available | Monthly limit after release |
| --- | ---: | ---: |
| Day 1 | 500 | 500 |
| Day 8 | 500 | 1,000 |
| Day 15 | 500 | 1,500 |
| Day 22 | 500 | 2,000 |

![Illustrative weekly plan: four releases of 500 credits increase the monthly limit to 2,000.](assets/release-timeline.svg)

Unused released credits remain available within the month. The schedule changes when capacity becomes available; the total monthly budget stays at the amount you choose.

## Get started with Codex

You can ask Codex to check the setup and run the fictional example for you.

1. [Download the starter kit](https://raw.githubusercontent.com/openai/openai-cookbook/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/assets/chatgpt-usage-budget-starter.zip) and extract it.
2. Open the extracted **chatgpt-usage-budget-starter** folder as a project in the Codex app.
3. Paste this prompt:

   ```text
   Read docs/get-started.md and follow its preview request.
   Check the available runtime and run the fictional preview. Explain the
   proposed limits in plain language. Keep workspace changes and scheduling off.
   ```

Codex checks for a suitable existing runtime, including a bundled one when available. After the preview, you can choose a budget, release schedule, and small group for a pilot. The [step-by-step setup guide](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/get-started.md) includes the full prompt and the expected result.

### Do I need Node.js?

**The browser example needs no Node.js.** The downloadable controller uses Node.js 24 or later, the software that runs its JavaScript. Codex can find and use an approved existing installation, so you do not need to know Node commands to try the example.

If that runtime is unavailable on your computer, use the browser example to choose a plan and ask Codex to prepare the setup request for your IT team. The controller can run on an approved managed host; Node does not have to be installed on every admin's computer.

The Admin API itself does not require Node. Your technical team can use other tools, including PowerShell or Python, to call it. The included controller implements the scheduling policy, recovery, and restoration in JavaScript; another implementation needs those behaviors too.

## Choose how to release the budget

| Approach | When it helps |
| --- | --- |
| Scheduled releases | Make a chosen amount available each hour, day, week, or custom interval. Use this to help a group pace a monthly allocation. |
| Usage-based increases | Give selected active users additional headroom based on recent observed consumption, up to the monthly maximum you set. |

Different populations can use different amounts and schedules through separate, reviewed configurations. For example, a project team might use weekly releases while a small group of power users uses usage-based increases. Keep each person in one active controller configuration.

See [policy configuration and examples](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/operations.md#choose-a-policy) for the calculations and settings. To help people understand their allowance, communicate the monthly budget, amount currently available, and next release date through your existing channels.

## Start with a pilot, then deploy for ongoing use

Use a local run or Codex automation to test the approach with a small group and confirm its value. For ongoing workspace credit management, run the controller on **organization-managed infrastructure**, such as a managed virtual machine or cloud service, with monitoring and a team responsible for operation.

![Try a small pilot locally or with Codex, then run ongoing releases on organization-managed infrastructure.](assets/control-flow.svg)

| What you want to do | Guide |
| --- | --- |
| Try the example with Codex | [Get started](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/get-started.md) |
| Test a scheduled Codex pilot | [Set up a Codex pilot](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/codex.md) |
| Run on a managed computer or server | [Set up a managed host](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/local.md) |
| Deploy using your AWS account | [Deploy on AWS](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/aws.md) |

The AWS guide provides a deployment template and setup instructions. Your technical team can adapt the controller to other infrastructure your organization operates. Scheduled releases should run independently of an individual's computer.

## Prepare a reviewed enrollment

Before connecting a live workspace, choose the people included, confirm their current settings and monthly period, and review the proposed changes. Follow [the configuration and enrollment guide](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/operations.md#prepare-a-reviewed-enrollment). A preview shows the proposed limits before applying them.

## Stop, restore, and renew

The controller saves the original settings and records its changes. Follow [the stop and restore procedure](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/operations.md#stop-restore-and-renew) when ending a pilot or changing its policy. Review a fresh enrollment for the next monthly period.

## Run the example from a terminal

For readers who prefer commands, open the extracted starter folder, or `examples/chatgpt/daily_usage_limits` in the repository. With Node.js 24 or later and npm available, run:

```bash
npm test
npm run demo
```

The demo uses three fictional members to show a preview, a simulated update, the next release, and restoration. See the [verification guide](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/verification.md) and [API contract](https://github.com/openai/openai-cookbook/blob/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/docs/api-contract.md) for implementation details.
