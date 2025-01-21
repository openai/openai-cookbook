# GPT Action Library: GRID

## Introduction

This page provides an instruction & guide for building a GPT Action for a specific application (e.g. Custom GPT). Before you proceed, make sure to first familiarize yourself with the following information:
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Buliding a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

This particular GPT Action offers an overview of how to connect a GPT to **GRID**, unlocking even more value from ChatGPT by equipping it with the power of a spreadsheet engine.

### Value + Example Business Use Cases

**Value**: Users can now leverage ChatGPT's natural language capability to interact with your spreadsheets, calculating results exactly like in your spreadsheet software. Whether analyzing financial forecasts, exploring pricing scenarios, or calculating ROI, your GPT becomes a powerful tool for decision-making.

**Example Use Cases**:
- Users can analyze finanical forecasts
- Users can explore pricing scenarios
- Users can calculate return of investment (ROI)

## Application Information

GRID brings the power of language to spreadsheets, assigning intuitive labels to cells and ranges. This allows AI to reference and interact with spreadsheets, bringing data and logic to natural language communication. Fully compatible with Excel and Google Sheets, GRID’s spreadsheet engine can run even the most complicated models at scale, providing reliable and verifiable calculations.


### Application Key Links

Check out these links from the application before you get started:
- Application Website: https://www.grid.is/
- Frequently asked questions: https://www.grid.is/faq

## ChatGPT Steps

### Add your spreadsheet to GRID

[Sign up for GRID](https://alpha.grid.is/user/login) and either upload your spreadsheet or connect a cloud-based one for automatic updates.

### Custom GPT Guide 

In GRID you can follow a step-by-step guide to setup your custom GPT. Below is a quick overview of the setup process.

#### Copy the GPT instructions

Once you've created a custom GPT copy the instructions from GRID to your custom GPT, as shown in the GIF below to.

![gpt-grid-instructions.gif](../../../../images/gpt-actions-grid-instructions.gif
)

GRID scans your spreadsheet to find text labels that describe the contents of specific cells and automatically adds them to the instructions. These instructions also include a unique identifier for your spreadsheet, ensuring that requests are directed to the correct place. Since the instructions are dynamic and unique to each spreadsheet you upload, make sure to copy them each time you use a new spreadsheet.

#### Copy the API Key

Follow the steps in the GIF below to find and copy your API key from GRID. Paste it into the custom GPT and make sure to add it as a Bearer token.

![gpt-grid-api-key.gif](../../../../gpt-actions-grid-api-key.gif)


#### Copy the schema

Copy the OpenAPI schema from GRID and paste it into the custom GPT to define how the AI interacts with your spreadsheet.

![gpt-grid-schema.gif](../../../../images/gpt-actions-grid-schema.gif)


#### Now You Are Ready to work with Your Spreadsheet!

Your custom GPT is now connected to GRID. You can ask questions, run calculations, and explore scenarios using natural language.

![gpt-grid-chat.gif](../../../../images/gpt-actions-grid-chat.gif)

### FAQ & Troubleshooting

If you have any questions or run into any issues, visit our [FAQ & Troubleshooting page](https://alpha.grid.is/faq) for detailed guidance and solutions.