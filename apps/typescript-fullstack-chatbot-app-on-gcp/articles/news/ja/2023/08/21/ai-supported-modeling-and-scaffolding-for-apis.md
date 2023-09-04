---
id: ai-supported-modeling-and-scaffolding-for-apis
title: オープンソースアプリフレームワーク "Skeet" にAI開発サポート機能を追加。開発者の生産性をさらに向上させます。
category: プレスリリース
thumbnail: /news/2023/08/21/ai-supported-modeling-and-scaffolding-for-apis.png
---

ELSOUL LABO B.V. (エルソウルラボ, 本社: オランダ・アムステルダム) は、オープンソース の TypeScript フルスタックサーバーレスアプリフレームワーク "Skeet" Version 1.4.0 のリリースを発表しました。

Skeet は GCP (Google Cloud) と Firebase 上にフルスタックアプリを構築できるオープンソースの TypeScript 製サーバーレスフレームワークです。

API サーバーから Web・iOS・Android アプリまですべてを TypeScript で爆速開発することができます。

今回のアップデートにより、Skeet は独自の AI コンソールを実装しました。今後 AI による開発サポートがさらに充実していきます。

ツールの裏側では、OpenAI 社製 の ChatGPT や Google 製 の Vertex AI といった API を活用しており、それぞれ Skeet を使った開発のサポートに特化したモデルを構築しています。

Skeet は、AI による開発サポートを通じて、開発者の生産性をさらに向上させることを目指しています。

Skeet CLI (GitHub): https://github.com/elsoul/skeet-cli

## Skeet AI による開発サポート

![Skeet AI](/news/2023/08/21/skeet-ai-prisma.jpg)

一般的なチャットサポートに加え、 Prisma モデリングに特化したサポートをリリースしました。作りたいアプリの内容を簡単な文章で入力するだけで、Skeet が自動的に Prisma 形式のデータモデルを提案します。

データモデルが用意できれば、Skeet はワン・コマンド(skeet g scaffold)で、そのデータモデルの内容の GraphQL API サーバーに必要なコード(CRUD)を自動生成します。

Prisma & Skeet がデータマイグレーションを完全に管理するため、開発者は Prisma 形式のデータモデルだけを編集すれば、マイグレーションファイルから GraphQL API サーバーのコードまで、アプリ構成に必要なコードが自動生成されます。

開発者はそれぞれのアプリごとに特有のロジックだけに集中することができ、開発効率が大幅に向上します。

Skeet はこのようなアプリコードの自動生成だけでなく、サーバーレス環境も自動で構築するため、作ったアプリをデプロイするときも心配ありません。

このような爆速開発環境を用意することで、グローバル社会全体でアプリによる問題解決を促進させていくことを目指しています。

今後も AI による多岐にわたる開発サポートを充実させ、より速く、より便利な開発環境を構築してまいります。

Skeet は世界中すべてのアプリケーション開発現場の開発・メンテナンスコストを削減、開発者体験を向上させるためにオープンソースとして開発されています。

詳しくは公式ドキュメントを御覧ください。

Skeet ドキュメント: https://skeet.dev/ja/
