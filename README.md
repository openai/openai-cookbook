# OpenAI Cookbook

The OpenAI Cookbook shares example code for accomplishing common tasks with the [OpenAI API].

To run these examples, you'll need an OpenAI account and associated API key ([create a free account][API Signup]).

Most code examples are written in Python, though the concepts can be applied in any language.

## Guides & examples

* API usage
  * [How to handle rate limits](examples/How_to_handle_rate_limits.ipynb)
    * [Example parallel processing script that avoids hitting rate limits](examples/api_request_parallel_processor.py)
  * [How to count tokens with tiktoken](examples/How_to_count_tokens_with_tiktoken.ipynb)
  * [How to stream completions](examples/How_to_stream_completions.ipynb)
* GPT-3
  * [Guide: How to work with large language models](how_to_work_with_large_language_models.md)
  * [Guide: Techniques to improve reliability](techniques_to_improve_reliability.md)
  * [How to use a multi-step prompt to write unit tests](examples/Unit_test_writing_using_a_multi-step_prompt.ipynb)
  * [Text writing examples](text_writing_examples.md)
  * [Text explanation examples](text_explanation_examples.md)
  * [Text editing examples](text_editing_examples.md)
  * [Code writing examples](code_writing_examples.md)
  * [Code explanation examples](code_explanation_examples.md)
  * [Code editing examples](code_editing_examples.md)
* Embeddings
  * [Text comparison examples](text_comparison_examples.md)
  * [How to get embeddings](examples/Get_embeddings.ipynb)
  * [Question answering using embeddings](examples/Question_answering_using_embeddings.ipynb)
  * [Semantic search using embeddings](examples/Semantic_text_search_using_embeddings.ipynb)
  * [Recommendations using embeddings](examples/Recommendation_using_embeddings.ipynb)
  * [Clustering embeddings](examples/Clustering.ipynb)
  * [Visualizing embeddings in 2D](examples/Visualizing_embeddings_in_2D.ipynb) or [3D](examples/Visualizing_embeddings_in_3D.ipynb)
  * [Embedding long texts](examples/Embedding_long_inputs.ipynb)
* Fine-tuning GPT-3
  * [Guide: best practices for fine-tuning GPT-3 to classify text](https://docs.google.com/document/d/1rqj7dkuvl7Byd5KQPUJRxc19BJt8wo0yHNwK84KfU3Q/edit)
  * [Fine-tuned classification](examples/Fine-tuned_classification.ipynb)
* DALL-E
  * [How to generate and edit images with DALL-E](examples/dalle/Image_generations_edits_and_variations_with_DALL-E.ipynb)
* Azure OpenAI (alternative API from Microsoft Azure)
  * [How to get completions from Azure OpenAI](examples/azure/completions.ipynb)
  * [How to get embeddings from Azure OpenAI](examples/azure/embeddings.ipynb)
  * [How to fine-tune GPT-3 with Azure OpenAI](examples/azure/finetuning.ipynb)

## Related resources

Beyond the code examples here, you can learn about the [OpenAI API] from the following resources:

* Try out the API in the [OpenAI Playground]
* Read about the API in the [OpenAI Documentation]
* Discuss the API in the [OpenAI Community Forum]
* Look for help in the [OpenAI Help Center]
* See example prompts in the [OpenAI Examples]
* Play with a free research preview of [ChatGPT]
* Stay up to date with the [OpenAI Blog]

## Contributing

If there are examples or guides you'd like to see, feel free to suggest them on the [issues page].

[ChatGPT]: https://chat.openai.com/
[OpenAI API]: https://openai.com/api/
[API Signup]: https://beta.openai.com/signup
[OpenAI Playground]: https://beta.openai.com/playground
[OpenAI Documentation]: https://beta.openai.com/docs/introduction
[OpenAI Community Forum]: https://community.openai.com/top?period=monthly
[OpenAI Help Center]: https://help.openai.com/en/
[OpenAI Examples]: https://beta.openai.com/examples
[OpenAI Blog]: https://openai.com/blog/
[issues page]: https://github.com/openai/openai-cookbook/issues
