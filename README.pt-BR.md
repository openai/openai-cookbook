# OpenAI Cookbook

O OpenAI Cookbook compartilha exemplos de código para realizar tarefas comuns com a [OpenAI API].

Para executar estes exemplos, você devera ter uma conta OpenAI e chave API associada ([crie uma conta gratuita][api signup]).

A maioria dos códigos de exemplo são escritos em Python, mas os conceitos podem ser aplicados em qualquer linguagem.

[![Abrir em GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://github.com/codespaces/new?hide_repo_select=true&ref=main&repo=468576060&machine=basicLinux32gb&location=EastUs)

## Adicionado Recentemente 🆕 ✨

- [Como formatar a entrada para modelos ChatGPT](examples/How_to_format_inputs_to_ChatGPT_models.ipynb) [1 Mar, 2023]
- [Usando Banco de Dados de Vetores para Pesquisa de Incorporação com Redis](https://github.com/openai/openai-cookbook/tree/main/examples/vector_databases/redis) [15 Fev, 2023]
- [Website de Perguntas e Respostas com Incorporação](https://github.com/openai/openai-cookbook/tree/main/apps/web-crawl-q-and-a) [11 Fev, 2023]
- [Arquivar Perguntas e Respostas com Incorporação](https://github.com/openai/openai-cookbook/tree/main/apps/file-q-and-a) [11 Fev, 2023]
- [Visualizar Incorporação em Pesos e Tendencias](https://github.com/openai/openai-cookbook/blob/main/examples/Visualizing_embeddings_in_W%26B.ipynb) [9 Fev, 2023]
- [Recuperação Aprimorada Generativa de Respostas de Perguntas com Pinecone](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/pinecone/Gen_QA.ipynb) [8 Fev, 2023]


## Guias e exemplos

- Uso de API
  - [Como lidar com limites de taxa](examples/How_to_handle_rate_limits.ipynb)
    - [Exemplo de código de processamento paralelo que evita atingir limites de taxa](examples/api_request_parallel_processor.py)
  - [Como contar tokens com tiktoken](examples/How_to_count_tokens_with_tiktoken.ipynb)
  - [Como transferir conclusões](examples/How_to_stream_completions.ipynb)
- ChatGPT
  - [Como formatar entradas para modelos ChatGPT](examples/How_to_format_inputs_to_ChatGPT_models.ipynb)
- GPT-3
  - [Guia: Como trabalhar com grandes modelos de linguagem](how_to_work_with_large_language_models.md)
  - [Guia: Técnicas para aperfeiçoar confiabilidade](techniques_to_improve_reliability.md)
  - [Como usar um prompt de múltiplas etapas para escrever testes de unidade](examples/Unit_test_writing_using_a_multi-step_prompt.ipynb)
  - [Exemplos de escrita de texto](text_writing_examples.md)
  - [Exemplos de explicação de texto](text_explanation_examples.md)
  - [Exemplos de edição de texto](text_editing_examples.md)
  - [Exemplos de escrita de codigo](code_writing_examples.md)
  - [Exemplos de explicação de codigo](code_explanation_examples.md)
  - [Exemplos de edição de codigo](code_editing_examples.md)
- Incorporação
  - [Exemplos de comparação de texto](text_comparison_examples.md)
  - [Como obter incorporações](examples/Get_embeddings.ipynb)
  - [Respondendo questões utilizando incorporação](examples/Question_answering_using_embeddings.ipynb)
  - [Pesquisa de semântica utilizando incorporação](examples/Semantic_text_search_using_embeddings.ipynb)
  - [Recomendações utilizando incorporação](examples/Recommendation_using_embeddings.ipynb)
  - [Agrupando incorporações](examples/Clustering.ipynb)
  - [Visualizando incorporações em 2D](examples/Visualizing_embeddings_in_2D.ipynb) ou [3D](examples/Visualizing_embeddings_in_3D.ipynb)
  - [Incorporando textos longos](examples/Embedding_long_inputs.ipynb)
- Afinando GPT-3
  - [Guia: melhores praticas para afinar GPT-3 para classificar texto](https://docs.google.com/document/d/1rqj7dkuvl7Byd5KQPUJRxc19BJt8wo0yHNwK84KfU3Q/edit)
  - [Afinando classificação](examples/Fine-tuned_classification.ipynb)
- DALL-E
  - [Como gerar e editar imagens com DALL-E](examples/dalle/Image_generations_edits_and_variations_with_DALL-E.ipynb)
- Azure OpenAI (API alternativa da Microsoft Azure)
  - [Como usar ChatGPT com Azure OpenAI](examples/azure/chat.ipynb)
  - [Como obter conclusões da Azure OpenAI](examples/azure/completions.ipynb)
  - [Como obter incorporações da Azure OpenAI](examples/azure/embeddings.ipynb)
  - [Como afinar GPT-3 com Azure OpenAI](examples/azure/finetuning.ipynb)
- Apps
  - [Arquivar Perguntas e Respostas](apps/file-q-and-a/)
  - [Rastreador de Perguntas e Respostas](apps/web-crawl-q-and-a)

## Recursos relacionados

Além dos exemplos de códigos aqui, você pode aprender sobre o [OpenAI API] pelos seguintes recursos:

- Teste a API no [OpenAI Playground]
- Leia sobre a API na [OpenAI Documentation]
- Discuta sobre a API no [OpenAI Community Forum]
- Procure por ajuda no [OpenAI Help Center]
- Veja exemplos de prompts em [OpenAI Examples]
- Brinque com uma visualização gratuita de pesquisa do [ChatGPT]
- Mantenha-se atualizado com o [OpenAI Blog]

## Contribuindo

Se existem exemplos ou guias você gostaria de ver, sinta-se livre para sugeri-los na [página de problemas].

[chatgpt]: https://chat.openai.com/
[openai api]: https://openai.com/api/
[api signup]: https://beta.openai.com/signup
[openai playground]: https://beta.openai.com/playground
[openai documentation]: https://beta.openai.com/docs/introduction
[openai community forum]: https://community.openai.com/top?period=monthly
[openai help center]: https://help.openai.com/en/
[openai examples]: https://beta.openai.com/examples
[openai blog]: https://openai.com/blog/
[página de problemas]: https://github.com/openai/openai-cookbook/issues