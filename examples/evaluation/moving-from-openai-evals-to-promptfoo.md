OpenAI is winding down the Evals product and recommends [Promptfoo](https://www.promptfoo.dev/) for continuing and extending your evaluation workflows. OpenAI Evals lets you export supported evaluations as runnable Promptfoo configs and separately preserve results from past runs.

Promptfoo is an open-source CLI and library for evaluating and red-teaming AI apps and agents. It gives you a more flexible way to run, maintain, and extend your evals locally or in CI.

## What Changes When You Move to Promptfoo

OpenAI Evals and Promptfoo share the same core building blocks: test data, prompts, providers/models, and criteria for scoring outputs. For supported evals, the exported Promptfoo configuration carries these pieces into a runnable evaluation, so you can continue testing the same behavior in Promptfoo.

The main difference is the workflow. OpenAI Evals is managed in the OpenAI Platform, where evaluations, runs, results, and related dataset workflows are available in the dashboard. Promptfoo is centered on a portable configuration file and CLI workflow. You can keep evaluations alongside your application code, run them locally or in CI, and adapt them as your testing needs evolve.

| OpenAI Evals | Promptfoo |
| --- | --- |
| Evaluations and results are managed in the OpenAI Platform dashboard. | Evaluations are defined in a config file and run with the CLI or in CI. |
| Graders are configured as testing criteria in an eval. | Grading behavior is configured as assertions and metrics. |
| Runs are tied to the Platform evaluation workflow. | Runs can be integrated into development, testing, and deployment workflows. |
| Platform features such as dataset review and prompt iteration remain in OpenAI. | Provider selection and evaluation customization are managed in Promptfoo. |

Promptfoo does not simply reproduce the OpenAI Evals interface in another tool. It provides a more portable, code-oriented workflow for maintaining, running, and extending evaluations over time.

## Migrate an Evaluation to Promptfoo

OpenAI Evals lets you export supported evaluations as runnable Promptfoo configurations, so you can continue running and extending your evals in Promptfoo. Historical result exports are separate: you can import them when you want previous OpenAI Evals runs available in Promptfoo.

### Before You Start

- [Install Promptfoo](https://www.promptfoo.dev/docs/installation/).
- An existing OpenAI Evals evaluation.
- An API key for the model provider used in your eval, such as `OPENAI_API_KEY`.

### Export a Runnable Promptfoo Configuration

1. Open the evaluation in the [OpenAI Platform dashboard](https://platform.openai.com/evaluation?tab=evals).
2. Select a completed run to use as the basis for the exported configuration. If your evaluation does not have a completed run yet, run it once before exporting.
3. Open the **Export** menu and select **Download runnable Promptfoo config**.
4. Download the Promptfoo configuration file and review any migration warnings before running it.

> Screenshot placeholder: OpenAI Evals export menu with **Download runnable Promptfoo config** visible.

### Run the Exported Evaluation in Promptfoo

Run a fresh evaluation and open the results viewer:

```bash
promptfoo eval -c <downloaded-config-file> --no-cache
promptfoo view
```

`eval` creates a new Promptfoo evaluation run, while `view` opens its results locally. This new run is separate from any previously completed OpenAI Evals runs.

If you modify the exported configuration or encounter a configuration error, validate it before retrying:

```bash
promptfoo validate config -c <downloaded-config-file>
```

![Promptfoo results view after running the exported evaluation](/images/promptfoo-custom-example-view.png)

### Verify the Migrated Evaluation

After your first Promptfoo run, review the results to confirm that the evaluation behaves as expected. If the export included warnings or you manually changed the configuration, compare the affected prompts, assertions, and outputs before using the eval in an ongoing workflow.

Similarity-based scoring may not produce identical numerical results across systems. Any manually recreated grader, especially an LLM-as-a-judge grader, should be validated before you rely on it for regression decisions.

### Preserve Historical Results

If you want past OpenAI Evals runs visible in Promptfoo, download your results from the export menu and import the downloaded file:

```bash
promptfoo import <downloaded-results-file>
promptfoo view
```

This preserves past run results for reference. It does not create the runnable Promptfoo configuration used for future evaluation runs.

### Cases That Require Manual Setup

Some evaluations may require additional setup in Promptfoo.

| Situation | What to do |
| --- | --- |
| A runnable configuration cannot be exported. | Recreate the evaluation in Promptfoo. Import historical results separately, if needed. |
| A grader is not included in the exported configuration. | Recreate it as a Promptfoo assertion and verify its behavior before relying on it. |
| A tool, agent, or custom provider workflow is not reproduced. | Configure that workflow in Promptfoo and test it before using the migrated eval. |

### Customize Your Workflow in Promptfoo

Once your migrated evaluation is working as expected, you can use Promptfoo to expand your test coverage, run evals in CI, and add red-team testing.

If you use Codex, see [Add evals to your AI application](/codex/use-cases/ai-app-evals) to build and maintain Promptfoo eval suites with the Promptfoo Codex plugin.

### Next Steps

- [Install Promptfoo](https://www.promptfoo.dev/docs/installation/)
- [Configure evaluations in Promptfoo](https://www.promptfoo.dev/docs/configuration/guide/)
- [Configure assertions and expected outputs](https://www.promptfoo.dev/docs/configuration/expected-outputs/)
- [Import historical results](https://www.promptfoo.dev/docs/usage/command-line/#promptfoo-import-filepath)
- [Run Promptfoo in CI/CD](https://www.promptfoo.dev/docs/integrations/ci-cd/)
