# Deprecation of Answers, Classification, and Search

In 2021, OpenAI released specialized endpoints in beta for Answers, Classification, and Search.

While these specialized endpoints were convenient, they had two drawbacks:

1. These specialized endpoints were eclipsed by techniques that achieved better results.
2. These specialized endpoints were more difficult to customize and optimize for individual use cases.

As a result, **the Answers, Classifications, and Search endpoints are being deprecated.**

## Timeline of deprecation

For those who have not used these endpoints, nothing will change except that access will no longer be available.

**For existing users of these endpoints, access will continue until December 3, 2022.** Before that date, we strongly encourage developers to switch over to newer techniques which produce better results.

## How to transition

We've written guides and code examples for transitioning from the deprecated API endpoints to better methods.

### Answers

[Guide: How to transition off the Answers endpoint](https://help.openai.com/en/articles/6233728-answers-transition-guide)

* Option 1: transition to embeddings-based search **(recommended)**
  * Example code: [Semantic_text_search_using_embeddings.ipynb](../examples/Semantic_text_search_using_embeddings.ipynb)

* Option 2: reimplement Answers endpoint functionality
  * Example code: [answers_functionality_example.py](answers_functionality_example.py)

### Classification

[Guide: How to transition off the Classifications endpoint](https://help.openai.com/en/articles/6272941-classifications-transition-guide)

* Option 1: transition to fine-tuning **(recommended)**
  * Example code: [Fine-tuned_classification.ipynb](../examples/Fine-tuned_classification.ipynb)
* Option 2: transition to embeddings
  * Example code: [Semantic_text_search_using_embeddings.ipynb](../examples/Semantic_text_search_using_embeddings.ipynb)
* Option 3: reimplement Classifications endpoint functionality
  * Example code: [classification_functionality_example.py](classification_functionality_example.py)

### Search

[Guide: How to transition off the Search endpoint](https://help.openai.com/en/articles/6272952-search-transition-guide)

* Option 1: transition to embeddings-based search **(recommended)**
  * Example code: [Semantic_text_search_using_embeddings.ipynb](../examples/Semantic_text_search_using_embeddings.ipynb)
* Option 2: reimplement Search endpoint functionality
  * Example code: [search_functionality_example.py](search_functionality_example.py)
