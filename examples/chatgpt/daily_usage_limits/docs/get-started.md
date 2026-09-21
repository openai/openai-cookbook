# Get started

Try a weekly release plan with three fictional people, then choose the amounts and schedule for your organization. The example uses a 2,000-credit monthly allocation released in 500-credit weekly portions.

## Download the starter kit

1. [Download the starter ZIP](https://raw.githubusercontent.com/openai/openai-cookbook/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/assets/chatgpt-usage-budget-starter.zip) and extract it.
2. Open the `chatgpt-usage-budget-starter` folder. It contains `README.md`, `docs`, `src`, and `assets`.
3. Choose one of the paths below.

You can explore the amounts and schedules immediately by opening `assets/release-explorer.html` in your browser.

## Run with Node.js

With Node.js 24 or later installed, open a terminal or PowerShell in the extracted folder and run:

```bash
node src/demo.mjs
```

The command uses the files in the starter kit. It previews the first release, applies it to fictional users, advances to the next release, and restores the starting settings. It also simulates an interrupted update and a conflicting admin edit, then shows recovery and restoration.

Look for each person's 2,000-credit monthly limit changing to a first release of 500, then increasing to 1,000 at the next release. All changes in this example stay in the local simulator.

## Let Codex help

Open the extracted **chatgpt-usage-budget-starter** folder as a project in the Codex app. Paste this request:

```text
Run this starter kit's fictional example with node src/demo.mjs, using an
available Node.js 24 or later runtime. Show me each person's starting limit,
first release, next release, and monthly maximum. Keep this session local
and use the example data.

If the required software is unavailable, help me prepare the managed
environment setup described in docs/get-started.md.

After the example, help me choose a monthly budget, release amount,
schedule, and group of people for a pilot.
```

Codex checks the available software and runs the example. Review the release amounts it shows, then describe the plan you want to try.

## Use a managed environment

Run the starter kit on a managed computer, virtual machine, or cloud environment your organization provides. This is also a path for admins whose computers cannot run the required software.

Give your technology team the starter kit and this setup request:

> Set up a ChatGPT usage-budget pilot with Node.js 24 or later. Run `node src/demo.mjs` to walk through the weekly plan with example data. For the pilot, we will choose the participants, monthly budgets, release schedule, credential storage, and operating owner together.

Choose the [managed host guide](local.md) for macOS or Linux, or the [AWS deployment guide](aws.md) for the included cloud template. Your team can adapt the program to other managed infrastructure.

## Set up a pilot

Choose a small group and confirm its monthly usage period. Review each person's starting limit, the first release, and the monthly maximum using the [configuration and enrollment guide](operations.md#prepare-a-reviewed-enrollment).

Use the [Codex pilot guide](codex.md) to try scheduled runs. For ongoing workspace credit management, use a managed host or cloud service with monitoring and an operating owner.
