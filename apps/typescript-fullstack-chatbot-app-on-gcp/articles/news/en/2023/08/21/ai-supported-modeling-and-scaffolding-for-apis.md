---
id: ai-supported-modeling-and-scaffolding-for-apis
title: Open-source Application Framework "Skeet" Adds AI Development Support to Enhance Developer Productivity.
category: Press release
thumbnail: /news/2023/08/21/ai-supported-modeling-and-scaffolding-for-apis.png
---

ELSOUL LABO B.V. (located in Amsterdam, Netherlands) has announced the release of version 1.4.0 of the open-source TypeScript full-stack serverless application framework "Skeet."

Skeet is an open-source TypeScript serverless framework that allows for the construction of full-stack applications on GCP (Google Cloud) and Firebase.

From the API server to Web, iOS, and Android apps, everything can be developed at lightning speed using TypeScript.

With this update, Skeet has implemented its unique AI console. Development support via AI will be further enhanced in the future.

Behind the scenes, the tool utilizes APIs such as OpenAI's ChatGPT and Google's Vertex AI, building models specialized in supporting development through Skeet.

Skeet aims to further enhance developer productivity through AI development support.

Skeet CLI (GitHub): https://github.com/elsoul/skeet-cli

## Development Support with Skeet AI

![Skeet AI](/news/2023/08/21/skeet-ai-prisma.jpg)

In addition to general chat support, we have released support specialized in Prisma modeling. By simply entering a brief description of the desired application, Skeet automatically proposes a data model in Prisma format.

Once the data model is ready, with just one command (skeet g scaffold), Skeet automatically generates the necessary code (CRUD) for the GraphQL API server based on the data model content.

As Prisma & Skeet fully manage data migration, by editing only the data model in Prisma format, all necessary code for application configuration, from migration files to GraphQL API server code, is automatically generated.

Developers can focus solely on the unique logic for each application, significantly improving development efficiency.

Skeet not only automates the generation of application code but also automatically constructs the serverless environment, so there's no need to worry when deploying the created app.

By providing such a rapid development environment, we aim to promote problem-solving through apps across global society.

We will continue to enhance a wide range of development support through AI, aiming to construct a faster and more convenient development environment.

Skeet is being developed as open-source to reduce development and maintenance costs for application development sites worldwide and to enhance the developer experience.

For more details, please see the official documentation.

Skeet Documentation: https://skeet.dev/en/
