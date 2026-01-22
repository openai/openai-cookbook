# GitHub Actions billing

Learn how usage of GitHub Actions is measured against your free allowance and how to pay for additional use.

## How use of GitHub Actions is measured

GitHub Actions usage is **free** for **self-hosted runners** and for **public repositories** that use standard GitHub-hosted runners. See [Choosing the runner for a job](/en/actions/writing-workflows/choosing-where-your-workflow-runs/choosing-the-runner-for-a-job#standard-github-hosted-runners-for-public-repositories).

For **private repositories**, each GitHub account receives a quota of free minutes, artifact storage, and cache storage for use with GitHub-hosted runners, depending on the account's plan. Any usage beyond the included amounts is billed to your account.

* **Minutes:** Your free minutes reset to the full amount at the start of each billing cycle. Minutes usage is charged to the repository owner, not the person who triggered the workflow runs.
* **Storage:** Storage charges accumulate throughout the month based on hourly usage. Your accrued storage charges reset to zero at the start of each billing cycle.

> \[!TIP]
> Anyone with write access to a repository can run actions. Any costs of running the actions are billed to the repository owner.

## How storage billing works

GitHub Actions storage billing operates on an **hourly accrual model**:

* **Continuous billing:** Storage charges accrue every hour based on your actual usage throughout the month
* **Monthly total:** Your bill reflects the total storage used throughout the month, measured in GB-Hours
* **Included amount:** The free storage allowance for your plan (for example, 50 GB on the Enterprise plan) is converted to an hourly rate for billing calculations
* **Shared storage:** Actions artifacts, Actions caches, and GitHub Packages storage all share the same pooled allowance. For more information, see [GitHub Packages billing](/en/billing/concepts/product-billing/github-packages).

### Understanding current vs. accrued storage

It's important to understand the difference between what you see on GitHub and what appears on your bill:

* **Current storage:** The amount of storage you have right now (visible in repository settings and the **Billing Overview** page)
* **Accrued storage:** The cumulative total of storage used throughout the billing cycle (determines your bill)

**When you delete artifacts:**

* Current storage decreases immediately
* Future hourly charges stop accumulating
* Storage already accrued during the current billing cycle remains in your total and will appear on your bill

**Example (30-day billing cycle):** If you store 10 GB of artifacts for 10 days, then delete everything on day 11:

* Days 1-10: Accruing 240 GB-Hours per day (10 GB × 24 hours)
* Day 11: Delete artifacts → current storage drops to 0 GB
* Days 11-30: Accruing 0 GB-Hours (no storage)
* Your bill: Shows 2,400 GB-Hours total (10 days × 240 GB-Hours/day)

Deleting artifacts reduces your current storage and prevents future charges, but does not remove charges already recorded for the time the storage existed.

### Storage measurement units

GitHub Actions measures storage in **binary gigabytes (GB)**, where:

* 1 GB = 2^30 bytes = 1,073,741,824 bytes
* This is also known as a gibibyte (GiB)
* 1 GB = 1,024 megabytes (MB)

**Billing calculations use GB-Hours:**

* 1 GB-Hour = 1 GB of storage for 1 hour
* Example: Storing 3 GB for 10 days = 720 GB-Hours (3 GB × 10 days × 24 hours)

Your monthly bill converts GB-Hours to GB-Months by dividing by the hours in the month (usually 720 hours for a 30-day month).

### Examples of how usage is measured

* If you run a workflow on a Linux runner and it takes 10 minutes to complete, you'll use 10 minutes of the repository owner's allowance. If the workflow generates a 10 MB artifact, then you'll also use 10 MB of the repository owner's artifact storage allowance.
* If you run a workflow that normally takes 10 minutes and it fails after 5 minutes because a dependency isn't available, you'll use 5 minutes of the repository owner's allowance. If you fix the problem and re-run the workflow successfully, in total you'll use 15 minutes of the repository owner's allowance.
* If you run a workflow that generates many log files and a long job summary, these files do not count towards the repository owner's artifact storage allowance.
* Cache storage usage is measured by the peak usage for each hour. Included usage is 10 GB per repository. For a given hour, if a repository has a peak cache usage of 15 GB, then the repository owner will be charged for the 5 GB of usage above the 10 GB included for that hour. The repository owner will only be charged if the repository cache storage limit has been configured higher than the included usage.
* Additional cache storage is $0.07 per GiB, per month.

## Free use of GitHub Actions

The following amounts of time for standard runners, artifact storage, and cache storage are included in your GitHub plan. At the start of each month, the minutes used by the account are reset to zero.

| Plan                          | Artifact storage | Minutes (per month) | Cache storage |
| ----------------------------- | ---------------- | ------------------- | ------------- |
| GitHub Free                   | 500 MB           | 2,000               | 10 GB         |
| GitHub Pro                    | 1 GB             | 3,000               | 10 GB         |
| GitHub Free for organizations | 500 MB           | 2,000               | 10 GB         |
| GitHub Team                   | 2 GB             | 3,000               | 10 GB         |
| GitHub Enterprise Cloud       | 50 GB            | 50,000              | 10 GB         |

The use of standard GitHub-hosted runners is free:

* In public repositories
* For GitHub Pages
* For Dependabot
* For the agentic features (public preview) in GitHub Copilot code review

> \[!NOTE]
>
> * Larger runners are always charged for, even when used by public repositories or when you have quota available from your plan.
> * The storage amounts shown are **shared** with GitHub Packages. This means your total storage across Actions artifacts, Actions caches, and Packages cannot exceed the included amount for your plan.

## Using more than your included quota

If your account does not have a valid payment method on file, usage is blocked once you use up your quota. Usage of larger runners is always blocked until you set up a payment method.

## Paying for additional GitHub Actions use

You pay for any additional use above your quota using the payment method set up for your GitHub account. See [Managing your payment and billing information](/en/billing/how-tos/set-up-payment/manage-payment-info).

For GitHub-hosted runners, storage is billed based on hourly usage of artifacts and caches throughout the month. Minutes are calculated based on the total processing time used by each runner type during the month.

* To estimate costs for paid usage, use the GitHub [pricing calculator](https://github.com/pricing/calculator?feature=actions).
* To view your current costs, see [Viewing your usage of metered products and licenses](/en/billing/managing-billing-for-your-products/viewing-your-product-usage).

> \[!NOTE]
> The billing dashboard may show your Actions usage as a dollar amount ("spend") rather than raw minutes. This amount already reflects any applicable minute costs.

### Baseline minute costs

Each type of runner hosted by GitHub has a cost per-minute that is determined by the operating system and processing power.

For example, jobs that run on Windows and macOS runners hosted by GitHub cost more to run than jobs on Linux runners.

| Operating system                     | Billing SKU  | Per-minute rate (USD) |
| ------------------------------------ | ------------ | --------------------- |
| Linux 1-core                         | `linux_slim` | $0.002                |
| Linux 2-core                         | `linux`      | $0.006                |
| Windows 2-core                       | `windows`    | $0.010                |
| macOS 3-core or 4-core (M1 or Intel) | `macos`      | $0.062                |

For full details of minute costs for different types of runners, see [Actions runner pricing](/en/billing/reference/actions-runner-pricing).

### Example minutes cost calculation for GitHub-hosted runners

For example, if your organization uses GitHub Team, using 5,000 minutes beyond the included quota on GitHub-hosted runners would have a total actions minutes cost of $38 USD currently, if you used baseline Linux and Windows runners.

* 5,000 (3,000 Linux and 2,000 Windows) minutes = $38 USD ($18 USD + $20 USD).
  * 3,000 Linux minutes at $0.006 USD per minute = $18 USD.
  * 2,000 Windows minutes at $0.010 USD per minute = $20 USD.

### Example artifact storage cost calculation

If you use 3 GB of artifact storage for 10 days of March and 12 GB for 21 days of March, your artifact storage usage would be:

* 3 GB x 10 days x (24 hours per day) = 720 GB-Hours
* 12 GB x 21 days x (24 hours per day) = 6,048 GB-Hours
* 720 GB-Hours + 6,048 GB-Hours = 6,768 GB-Hours
* 6,768 GB-Hours / (744 hours per month) = 9.0967 GB-Months

At the end of the month, GitHub rounds your artifact storage to the nearest MB. Therefore, your artifact storage usage for March would be 9.097 GB.

> \[!NOTE]
> GitHub updates your artifact storage space within a 6 to 12-hour window. If you delete artifacts, the available space will be reflected in your account during the next scheduled update.

### Example cache storage cost calculation

If you use 3 GB of cache storage for 10 days of March and 12 GB for 21 days of March, your cache storage usage would be:

| Usage (GBs)                | Billable   (GB-Hours)                    | Non billable   (GB-Hours)           |
| -------------------------- | ---------------------------------------- | ----------------------------------- |
| 3 GB for the first 10 days | 0 GB-Hours                               | 720 GB-Hours                        |
| 12 GB for the next 21 days | **2\*21 days\*24 hours = 1008 GB-Hours** | 10\*21 days\*24 hours=5040 GB-Hours |

For cached storage, billing charts and reports show only the cost of usage beyond the included 10 GB. At the end of the month, the Actions Cache Storage SKU would show a use of 1008 GB-Hours.

## Managing your budget for GitHub Actions

If your account does not have a valid payment method on file, usage is blocked once you use up your quota.

If you have a valid payment method on file, spending may be limited by one or more budgets. Check the budgets set for your account to ensure they are appropriate for your usage needs. See [Setting up budgets to control spending on metered products](/en/billing/managing-your-billing/using-budgets-control-spending).

<!-- expires 2026-01-10 -->

<!-- We should not need to mention these budgets in 2026, but check in billing-vnext for confirmation.-->

Accounts that have migrated from the old billing platform may contain automatically generated budgets that mirror their previous spending limits.

<!-- end expires 2026-01-10 -->

## Further reading

* [Understanding GitHub Actions](/en/actions/get-started/understand-github-actions)
* [Quickstart for GitHub Actions](/en/actions/get-started/quickstart)
