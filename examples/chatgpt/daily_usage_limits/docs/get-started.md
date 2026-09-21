# Get started

Try a weekly release plan with three fictional people, then choose the billing unit, amounts, and schedule for your organization. The examples use either 2,000 credits per month with 500-credit weekly releases or $200.00 per month with $50.00 weekly releases.

## Download the starter kit

1. [Download the starter ZIP](https://raw.githubusercontent.com/openai/openai-cookbook/codex/daily-usage-limits/examples/chatgpt/daily_usage_limits/assets/chatgpt-usage-budget-starter.zip) and extract it.
2. Open the `chatgpt-usage-budget-starter` folder. It contains `README.md`, `docs`, `src`, and `assets`.
3. Choose one of the paths below.

You can explore the amounts and schedules immediately by opening `assets/release-explorer.html` in your browser. Select **Credits** or **US dollars (USD)** to match the unit shown in your workspace's usage settings. **Both** displays independent credit and dollar examples for comparison.

| What you want to do | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Explore budgets in a browser | Open the HTML file | Open the HTML file | Open the HTML file |
| Run the fictional example with Node.js 24 or later | PowerShell or Terminal | Terminal | Terminal |
| Run scheduled changes for your workspace | AWS or a managed Linux host | Managed host or AWS | Managed host or AWS |

The included local service uses macOS or Linux. Windows admins can use their organization's managed Linux environment or [AWS CloudShell](aws.md#choose-your-setup-environment) in a browser to prepare the AWS deployment.

## Run with Node.js

With Node.js 24 or later installed, open a terminal or PowerShell in the extracted folder and run:

```bash
node src/demo.mjs --unit credit
```

For the dollar example, run:

```bash
node src/demo.mjs --unit usd
```

On Windows, open the extracted folder in File Explorer, right-click its background, and choose **Open in Terminal**. On macOS or Linux, open Terminal, type `cd `, drag the extracted folder into the window, and press Enter. Paste the command above.

The command uses the files in the starter kit and keeps its example data in memory. It previews the first release, applies it to fictional users, advances to the next release, and restores the starting settings. It also simulates an interrupted update and a conflicting admin edit, then shows recovery and restoration.

In the credit example, each person's 2,000-credit monthly limit changes to a first release of 500, then increases to 1,000 at the next release. In the dollar example, the $200.00 monthly limit changes to $50.00, then $100.00. All changes in these examples stay in the local simulator.

## Let Codex help

Open the extracted **chatgpt-usage-budget-starter** folder as a project in the Codex app. Paste this request:

```text
Help me choose credits or US dollars to match my workspace's billing unit.
Run this starter kit's fictional example with node src/demo.mjs --unit credit
or node src/demo.mjs --unit usd, using an available Node.js 24 or later runtime.
Show me each person's starting limit,
first release, next release, and monthly maximum. Keep this session local
and use the example data.

If the required software is unavailable, help me prepare the managed
environment setup described in docs/get-started.md.

After the example, help me choose amounts in that unit for the monthly budget
and release, a schedule, and a group of people for a pilot.
```

Codex checks the available software and runs the example. Review the release amounts it shows, then describe the plan you want to try.

## Use a managed environment

Run the starter kit on a managed computer, virtual machine, or cloud environment your organization provides. This is also a path for admins whose computers cannot run the required software.

Give your technology team the starter kit and this setup request:

> Set up a ChatGPT usage-budget pilot with Node.js 24 or later. Run `node src/demo.mjs` to walk through the weekly plan with example data. For the pilot, we will choose the participants, monthly budgets, release schedule, credential storage, and operating owner together.

Choose the [managed host guide](local.md) for macOS or Linux, or the [AWS deployment guide](aws.md) for the included cloud template. Your team can adapt the program to other managed infrastructure.

## Set up a pilot

Choose a workspace and a small group by user ID, email address, or workspace group ID, then confirm its billing unit and monthly usage period. Set `--unit credit` or `--unit usd` when you [configure the plan](operations.md#choose-the-billing-unit). You can also enroll all current workspace members after proving the setup with a smaller group. Review each person's starting limit, the first release, and the monthly maximum using the [configuration and enrollment guide](operations.md#prepare-a-reviewed-enrollment).

Use the [Codex pilot guide](codex.md) to try scheduled runs. For ongoing workspace budget management, use a managed host or cloud service with monitoring and an operating owner.

For later periods on AWS, use [guided renewal](aws.md#7-renew-the-next-period). Confirm the new dates and opening limits; the existing cloud setup, policy, and people carry forward.
