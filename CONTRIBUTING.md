# Contributing to the Cookbook

The OpenAI Cookbook is a community resource for practical patterns, runnable examples, and guides for building with OpenAI technologies. Contributions that fix an existing example or explain a useful workflow are welcome.

> Contributions are reviewed on a best-effort basis. We cannot guarantee when or whether a contribution will be reviewed or merged.

## Choose an issue or a pull request

- For a problem with an existing example or the Cookbook site, open a [problem report](https://github.com/openai/openai-cookbook/issues/new/choose). Name the affected file or page, describe the problem and the expected behavior, and include a small reproduction or screenshot when useful.
- For a new example or guide, follow the [new Cookbook submission steps](#before-opening-a-pr-for-a-new-cookbook).
- For other ideas, open a [feature request](https://github.com/openai/openai-cookbook/issues/new/choose).
- For a focused correction to existing content, you can open a pull request directly. Search existing issues and pull requests first, and link a related issue if there is one.

## Before opening a PR for a new Cookbook

1. Share the proposal in the Cookbook maintainers' review channel on Slack. Describe the use case and what readers will learn beyond existing examples. If you lack access, open or reuse a [feature request](https://github.com/openai/openai-cookbook/issues/new/choose) and wait for a maintainer to confirm they shared the proposal.
2. List each credited author's Cookbook ID under `authors` in [`registry.yaml`](registry.yaml). Check that each author has a profile with a working picture. To add or update a Cookbook profile, set `name`, `website`, and `avatar` under the same ID in [`authors.yaml`](authors.yaml). If the site manages that profile, ask a site maintainer to update it.
3. Confirm with each author whether the OpenAI employee badge should appear. Ask a site maintainer to verify eligibility and make any badge changes. Keep private review links and verification details out of public issues and PRs.
4. [Choose a tag](#choose-cookbook-tags) for the OpenAI capability the recipe teaches.

Ask the relevant product or partner team to review the draft when applicable. The finished Cookbook requires Developer Experience approval before publication.

## Place and publish content

- Put notebooks, Python scripts, and their related assets in `examples/<topic>/`. Put long-form guides in `articles/` and shared diagrams or screenshots in `images/`.
- Add an entry to [`registry.yaml`](registry.yaml) for new or relocated content that should appear on [cookbook.openai.com](https://cookbook.openai.com/). Match its `path` to the file. The registry schema requires `title`, `path`, `slug`, `tags`, and `authors`; also provide an accurate description and publication date.
- Keep large datasets outside the repository and explain how readers can obtain them.

### Choose Cookbook tags

Choose at least one registry tag for the capability the recipe teaches. The table groups tags by [Cookbook homepage topic](https://developers.openai.com/cookbook). For a recipe about embedding long inputs with `tiktoken`, use the `embeddings` tag and mention the library in the title or description.

| Homepage topic | Registry tags |
| --- | --- |
| Agents | `agents`, `agents-api`, `agents-sdk`, `agentkit`, `workspace-agents` |
| Agents API | `agents-api` |
| Audio | `audio`, `speech`, `speech-to-text`, `transcription`, `realtime` |
| ChatGPT | `chatgpt`, `gpt-actions-library`, `workspace-agents` |
| Codex | `codex` |
| Evals | `evals` |
| Fine-tuning | `fine-tuning`, `gpt-oss-fine-tuning`, `reinforcement-learning` |
| Guardrails | `guardrails`, `moderation` |
| Images | `images`, `image-generation` |
| Multimodal | `multimodal`, `images`, `vision`, `audio`, `speech`, `sora` |
| Open models | `open-models`, `gpt-oss`, `harmony` |
| Optimization | `fine-tuning`, `prompt-optimization`, `prompt-caching`, `latency`, `cost-api`, `usage-api`, `cost-management`, `batch` |
| Responses | `responses` |
| Retrieval | `retrieval`, `rag`, `embeddings` |
| Security | `security` |
| Sign-in with ChatGPT | `sign-in-with-chatgpt` |
| Text | `completions`, `prompt`, `prompt-engineering`, `structured-outputs`, `reasoning` |
| Tool use | `functions`, `mcp`, `tool calling` |

If no tag fits, explain the gap in the PR and suggest a tag and the homepage topic where readers would look for it. Maintainers update this table when a topic's tags change.

## Prepare and validate your change

1. Create and activate a Python virtual environment. Install the dependencies listed by the example you changed, such as its `requirements.txt`, and document any additional prerequisites.
2. Run changed notebooks from top to bottom. Clear execution counts before committing. For Python utilities, run a relevant self-check or test and include instructions to repeat it.
3. For changed notebooks, install `nbformat` and run the repository's structure check:

   ```bash
   python .github/scripts/check_notebooks.py
   ```

4. Review changed prose, code, links, and output for accuracy. Check that paths in `registry.yaml` resolve if you added or moved published content.

Read credentials from environment variables such as `OPENAI_API_KEY`; never commit API keys, tokens, or other secrets. List required variables and setup steps in the example. If an example calls an external service, explain the dependency and any credentials or cost involved. Mock responses or make service-dependent cells clearly opt-in where practical.

## Open a pull request

Use the [pull request template](.github/pull_request_template.md) to explain what changed and why. Include the validation you ran, link related issues, and add screenshots or output snippets when they help reviewers check the result.

### Rubric

- **Relevance:** The recipe teaches readers how to use an OpenAI capability in their own projects.
- **Uniqueness:** Search related Cookbook examples and documentation to verify that the recipe teaches something new.
- **Spelling and grammar:** Free of distracting errors.
- **Clarity:** Organized and understandable.
- **Correctness:** Claims and code have been checked; code runs as described.
- **Completeness:** Includes the context, references, and citations readers need.

Reviewers rate each area from 1 to 4. A submission needs at least 3 in every area to be accepted. Maintainers may ask for revisions.

## Find the right place for help

- **Cookbook examples or site:** Use a [Cookbook issue](https://github.com/openai/openai-cookbook/issues/new/choose) for a specific problem or a narrow question about an example.
- **OpenAI API usage:** Start with the [API documentation](https://developers.openai.com/api/docs); use the [developer community](https://community.openai.com/) for general questions. The Cookbook issue tracker is for problems with Cookbook content.
- **Codex:** For Codex CLI problems or feature requests, use the [Codex repository](https://github.com/openai/codex/issues). For other Codex support, use the [OpenAI Help Center](https://help.openai.com/).
- **OpenAI account or billing:** Use the [OpenAI Help Center](https://help.openai.com/).
- **Third-party service or library:** Report a problem with that integration to its maintainer. If a Cookbook example uses it incorrectly, identify the example in a Cookbook problem report.
