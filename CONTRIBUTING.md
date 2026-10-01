# Contributing to the Cookbook

The OpenAI Cookbook is a community resource for practical patterns, runnable examples, and guides for building with OpenAI technologies. Contributions that fix an existing example or explain a useful workflow are welcome.

> Contributions are reviewed on a best-effort basis. We cannot guarantee when or whether a contribution will be reviewed or merged.

## Choose an issue or a pull request

- For a problem with an existing example or the Cookbook site, open a [problem report](https://github.com/openai/openai-cookbook/issues/new/choose). Name the affected file or page, describe the problem and the expected behavior, and include a small reproduction or screenshot when useful.
- For an idea that needs discussion, open a [feature request](https://github.com/openai/openai-cookbook/issues/new/choose) describing the use case and proposed example.
- For a focused correction or a ready-to-review example, you can open a pull request directly. Search existing issues and pull requests first, and link a related issue if there is one.

Keep examples relevant to building with OpenAI technologies. Explain the task they solve, the prerequisites, and the choices a reader needs to understand or adapt them. Prefer a focused, reproducible contribution over a large collection of unrelated examples.

## Place and publish content

- Put notebooks, Python scripts, and their related assets in `examples/<topic>/`. Put long-form guides in `articles/` and shared diagrams or screenshots in `images/`.
- Add an entry to [`registry.yaml`](registry.yaml) for new or relocated content that should appear on [cookbook.openai.com](https://cookbook.openai.com/). Match its `path` to the file. The registry schema requires `title`, `path`, `slug`, `tags`, and `authors`; also provide an accurate description and publication date.
- [`authors.yaml`](authors.yaml) is optional for custom author information. Without an entry there, the site uses the author's GitHub profile. Use the same author slug in both files if you add custom attribution.
- Keep large datasets outside the repository and explain how readers can obtain them.

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

Use the [pull request template](.github/pull_request_template.md) to explain what changed and why. Include the validation you ran, link related issues, and add screenshots or output snippets when they help reviewers check the result. For new published content, complete the template's `registry.yaml` and optional `authors.yaml` checklist and review the submission against the rubric below.

### Rubric

The pull request template asks contributors to self-review these areas:

- **Relevance:** Useful to people building with OpenAI technologies.
- **Uniqueness:** Adds information beyond related Cookbook examples and documentation.
- **Spelling and grammar:** Free of distracting errors.
- **Clarity:** Organized and understandable.
- **Correctness:** Claims and code have been checked; code runs as described.
- **Completeness:** Includes the context, references, and citations readers need.

The template says reviewers rate each area from 1 to 4 and accept content scoring at least 3 in every area. Maintainers review contributions on a best-effort basis and may ask for revisions.

## Find the right place for help

- **Cookbook examples or site:** Use a [Cookbook issue](https://github.com/openai/openai-cookbook/issues/new/choose) for a specific problem or a narrow question about an example.
- **OpenAI API usage:** Start with the [API documentation](https://developers.openai.com/api/docs); use the [developer community](https://community.openai.com/) for general questions. The Cookbook issue tracker is for problems with Cookbook content.
- **Codex:** For Codex CLI problems or feature requests, use the [Codex repository](https://github.com/openai/codex/issues). For other Codex support, use the [OpenAI Help Center](https://help.openai.com/).
- **OpenAI account or billing:** Use the [OpenAI Help Center](https://help.openai.com/).
- **Third-party service or library:** Report a problem with that integration to its maintainer. If a Cookbook example uses it incorrectly, identify the example in a Cookbook problem report.
