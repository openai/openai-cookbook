## TypeScript FullStack Chatbot App on Google Cloud and Firebase

![Skeet Next.js Template](https://storage.googleapis.com/skeet-assets/imgs/samples/WebAppBoilerplate.png)

<p align="center">
  <a href="https://twitter.com/intent/follow?screen_name=ELSOUL_LABO2">
    <img src="https://img.shields.io/twitter/follow/ELSOUL_LABO2.svg?label=Follow%20@ELSOUL_LABO2" alt="Follow @ELSOUL_LABO2" />
  </a>
  <br/>

  <a aria-label="npm version" href="https://www.npmjs.com/package/@skeet-framework/cli">
    <img alt="" src="https://badgen.net/npm/v/@skeet-framework/cli">
  </a>
  <a aria-label="Downloads Number" href="https://www.npmjs.com/package/@skeet-framework/cli">
    <img alt="" src="https://badgen.net/npm/dt/@skeet-framework/cli">
  </a>
  <a aria-label="License" href="https://github.com/elsoul/skeet-cli/blob/master/LICENSE.txt">
    <img alt="" src="https://badgen.net/badge/license/Apache/blue">
  </a>
    <a aria-label="Code of Conduct" href="https://github.com/elsoul/skeet-cli/blob/master/CODE_OF_CONDUCT.md">
    <img alt="" src="https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg">
  </a>
</p>

## Using

Skeet Framework is a full-stack serverless framework for building web applications with TypeScript.

Doc: https://skeet.dev/

It includes:

- [Firebase - Serverless Platform](https://firebase.google.com/)
- [Google Cloud - Cloud Platform](https://cloud.google.com/)
- [Jest - Testing framework](https://jestjs.io/)
- [TypeScript - Type Check](https://www.typescriptlang.org/)
- [ESLint - Linter](https://eslint.org/)
- [Prettier - Formatter](https://prettier.io/)
- [Recoil - State Management](https://recoiljs.org/)
- [React i18n - Localization](https://react.i18next.com/)
- [Next.js - SSG Framework](https://nextjs.org/)
- [React - UI Framework](https://reactjs.org/)
- [Tailwind - CSS Framework](https://tailwindcss.com/)

## Usage

```bash
$ npm i -g firebase-tools
$ npm i -g @skeet-framework/cli
```

```bash
$ cd apps/typescript-fullstack-chatbot-app-on-gcp
$ skeet yarn i // choose root and skeet
$ skeet s
```

**※ You need OpenAI API key to get success for default test.**

_./functions/skeet/.env_
or
_./functions/skeet/.secret.local_

```bash
CHAT_GPT_KEY=your-key
CHAT_GPT_ORG=your-org
```

Open Firebase Emulator: http://localhost:4000

Open Front-end App: http://localhost:4200

For more information, visit Skeet Doc: https://skeet.dev/
