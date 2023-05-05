# OpenAI Cookbook

OpenAI Cookbookでは、[OpenAI API]を使用して一般的なタスクを実行するためのコード例を共有しています。

これらの例を実行するには、OpenAIアカウントとAPIキーが必要です（[無料アカウントを作成][api signup]）。

ほとんどのコード例はPythonで書かれていますが、どの言語でも概念を適用することができます。

[![GitHub Codespacesで開く](https://github.com/codespaces/badge.svg)](https://github.com/codespaces/new?hide_repo_select=true&ref=main&repo=468576060&machine=basicLinux32gb&location=EastUs)

## 最近追加または更新されたもの 🆕 ✨

- [埋め込みを使用した質問応答](examples/Question_answering_using_embeddings.ipynb) [2023年4月14日]
- [ベクターデータベースを使った埋め込み検索](examples/vector_databases/) [様々な日付]
- [ChatGPTと独自のデータを使って製品を強化する方法](apps/chatbot-kickstarter/powering_your_products_with_chatgpt_and_your_data.ipynb) [2023年3月10日]
- [ChatGPTモデルへの入力のフォーマット方法](examples/How_to_format_inputs_to_ChatGPT_models.ipynb) [2023年3月1日]


## ガイドと例

- APIの使用法
  - [レート制限の対処方法](examples/How_to_handle_rate_limits.ipynb)
    - [レート制限に達しない並列処理スクリプトの例](examples/api_request_parallel_processor.py)
  - [tiktokenを使ってトークンをカウントする方法](examples/How_to_count_tokens_with_tiktoken.ipynb)
  - [コンプリーションのストリーミング方法](examples/How_to_stream_completions.ipynb)
- ChatGPT
  - [ChatGPTモデルへの入力のフォーマット方法](examples/How_to_format_inputs_to_ChatGPT_models.ipynb)
  - [ChatGPTと独自のデータを使って製品を強化する方法](apps/chatbot-kickstarter/powering_your_products_with_chatgpt_and_your_data.ipynb)
- GPT
  - [ガイド: 大規模言語モデルの取り扱い方法](how_to_work_with_large_language_models.md)
  - [ガイド: 信頼性を向上させる技術](techniques_to_improve_reliability.md)
  - [マルチステッププロンプトを使ってユニットテストを書く方法](examples/Unit_test_writing_using_a_multi-step_prompt.ipynb)
- エンベディング
  - [テキスト比較の例](text_comparison_examples.md)
  - [エンベディングの取得方法](examples/Get_embeddings.ipynb)
  - [エンベディングを使った質問応答](examples/Question_answering_using_embeddings.ipynb)
  - [エンベディング検索のためのベクターデータベースの使用](examples/vector_databases/Using_vector_databases_for_embeddings_search.ipynb)
  - [エンベディングを使ったセマンティックテキスト検索](examples/Semantic_text_search_using_embeddings.ipynb)
  - [エンベディングを使ったレコメンデーション](examples/Recommendation_using_embeddings.ipynb)
  - [エンベディングのクラスタリング](examples/Clustering.ipynb)
  - [2Dでのエンベディングの可視化](examples/Visualizing_embeddings_in_2D.ipynb) または [3D](examples/Visualizing_embeddings_in_3D.ipynb)
  - [長いテキストのエンベディング](examples/Embedding_long_inputs.ipynb)
- GPT-3のファインチューニング
  - [ガイド: GPT-3をテキスト分類にファインチューニングするためのベストプラクティス](https://docs.google.com/document/d/1rqj7dkuvl7Byd5KQPUJRxc19BJt8wo0yHNwK84KfU3Q/edit)
  - [ファインチューニングされた分類](examples/Fine-tuned_classification.ipynb)
- DALL-E
  - [DALL-Eで画像を生成・編集する方法](examples/dalle/Image_generations_edits_and_variations_with_DALL-E.ipynb)
- Azure OpenAI (Microsoft Azureからの代替API)
  - [Azure OpenAIでChatGPTを使う方法](examples/azure/chat.ipynb)
  - [Azure OpenAIからコンプリーションを取得する方法](examples/azure/completions.ipynb)
  - [Azure OpenAIからエンベディングを取得する方法](examples/azure/embeddings.ipynb)
  - [Azure OpenAIでGPT-3をファインチューニングする方法](examples/azure/finetuning.ipynb)
- アプリ
  - [ファイルQ&A](apps/file-q-and-a/)
  - [WebクロールQ&A](apps/web-crawl-q-and-a)

## 関連リソース

ここで紹介したコードサンプル以外にも、[OpenAI API]に関する情報は以下のリソースから学ぶことができます。

- [ChatGPT]で実験する
- [OpenAI Playground]でAPIを試す
- [OpenAI Documentation]でAPIについて読む
- [OpenAI Community Forum]でAPIについて議論する
- [OpenAI Help Center]でヘルプを探す
- [OpenAI Examples]でサンプルを見る
- [OpenAI Blog]で最新情報を入手する

## 貢献

もし、見たいサンプルやガイドがあれば、[issues page]で提案してください。

[chatgpt]: https://chat.openai.com/
[openai api]: https://openai.com/api/
[api signup]: https://beta.openai.com/signup
[openai playground]: https://beta.openai.com/playground
[openai documentation]: https://beta.openai.com/docs/introduction
[openai community forum]: https://community.openai.com/top?period=monthly
[openai help center]: https://help.openai.com/en/
[openai examples]: https://beta.openai.com/examples
[openai blog]: https://openai.com/blog/
[issues page]: https://github.com/openai/openai-cookbook/issues
