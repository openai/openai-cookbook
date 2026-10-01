# Prior authorization AgentCore support code

The adjacent Cookbook notebook imports this package to keep the walkthrough concise. The `knowledge_base.py` module defines the Bedrock Managed Knowledge Base, S3 connector, and service-managed embedding configuration. The `runtime_source` directory contains the complete Python application and package manifest that the notebook validates, packages, and deploys to Amazon Bedrock AgentCore Runtime. Its retrieval module applies policy metadata filters before managed hybrid search and managed reranking.
