---
id: fine-tuning-with-gpt-35-turbo-on-skeet
title: ChatGPT、Vertex AI等の生成AIを簡単にカスタマイズして自社用に使いこなせるオープンソース"Skeet"がGPT-3.5のファインチューニングにも対応しました
category: プレスリリース
thumbnail: /news/2023/08/25/FineTuningWithGPT35Turbo.png
---

ELSOUL LABO B.V. (エルソウルラボ, 本社: オランダ・アムステルダム) は、ChatGPT、Vertex AI 等の生成 AI を簡単にカスタマイズして自社用に使いこなせるオープンソース "Skeet" のプラグイン "Skeet AI" の バージョン 1.4.0 リリースを発表しました。

Skeet は GCP (Google Cloud) と Firebase 上にフルスタックアプリを構築できるオープンソースの TypeScript 製サーバーレスフレームワークです。

API サーバーから Web・iOS・Android アプリまですべてを TypeScript で爆速開発することができます。

今回のアップデートにより、Skeet では TypeScript を使って GPT-3.5 の Fine-tuning を簡単に実行できるようになりました。

Skeet AI (GitHub): https://github.com/elsoul/skeet-ai

## ChatGPT の GPT-3.5 Turbo を使用したファインチューニング(Fine-tuning)

ファインチューニングの利点は、次のとおりです。

- 高品質な応答の生成
- より多くの例の適用
- コストの節約（トークン数、処理時間の削減）

初期のテストにおいてファインチューニングした「GPT-3.5 Turbo」は、特定の狭いタスクに関して「GPT-4」と同等、またはそれ以上のパフォーマンスを発揮できることが報告されています。

Skeet では、GPT-3.5 Turbo を使用したファインチューニングを簡単に実行でき、出来上がったモデルをアプリケーションに組み込む準備はできています。

ファインチューニングのためのデータセット(JSONL 形式)を様々なデータ形式(例えばドキュメントの Markdown 等)から作成するためのツールも提供するため、AI モデルのカスタマイズから、それを活かしたアプリケーションの開発までを一貫して爆速で行うことができます。

今後も AI を活用するための多岐にわたる開発サポートを充実させ、より速く、より便利な開発環境を構築してまいります。

Skeet は世界中すべてのアプリケーション開発現場の開発・メンテナンスコストを削減、開発者体験を向上させるためにオープンソースとして開発されています。

詳しくは公式ドキュメントを御覧ください。

Skeet ドキュメント: https://skeet.dev/ja/
