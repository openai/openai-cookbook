# Databricks Sandbox

Run an agent built with the OpenAI Agents API where OpenAI hosts the agent
harness and a Databricks sandbox executes the agent's shell and file tool calls.
Developers can configure network connectivity and file access within the
Databricks environment, providing greater control over how agents interact with
external systems and enterprise resources.

[Run the application-managed example](application_managed/README.md) using the
Databricks SDK for Python. Databricks Sandbox integrates with the Agents API in
application-managed provisioning mode.

This example does not include a webhook controller.
