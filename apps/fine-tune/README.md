
# Create JSONL to fine tune OpenAI's Chat Model

This application is built using Streamlit and helps users create a properly formatted Jsonl file. This file format is needed to fine-tune an OpenAi chat model.
This application is meant to be used locally please see our other version for a remote use. 

```python
data = {
    "messages": [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt_text},
        {"role": "assistant", "content": ideal_generated_text}
    ]
}
```

## Features

- **Fine-tune OpenAI & test the responses**: Provides an interface to fine-tune OpenAI models and test their responses.
- **Enter your OpenAI API Key:**: Allows you to enter your OpenAI API key.
- **Enter your message:**: Lets you enter a message to test the fine-tuned model.
- **Upload to OpenAI**: Allows you to upload fine-tuning data to OpenAI.
- **Append to output.jsonl**: Allows you to append data to a JSONL file.
- **Create fine-tuning job**: Lets you create a fine-tuning job with OpenAI.
- **Your OpenAI API key is not found in a .env file.**: Provides an option to save your API key securely in a .env file.
- **Enter your ORG_ID:**: Allows you to enter your OpenAI Organization ID.
- **Please provide your ORG_ID below to save it securely in a .env file.**: Provides an option to save your Organization ID securely in a .env file.



## Setup & Run

1. Clone the repository using:
   ```
   git clone https://github.com/openai/openai-cookbook.git
   ```
2. Navigate to the repository directory:
   ```
   cd openai-cookbook/app/fine=tune 
   ```
3. Install the required packages using:
   ```
   pip install -r requirements.txt
   ```
4. Run the Streamlit app using:
   ```
   streamlit run app.py
   ```

## Dependencies
- openai 
- streamlit
- jsonlines
- tiktoken
- numpy
- requests
- python-dotenv

## Feedback & Contributions

Feel free to raise issues, provide feedback, or make contributions to improve the application.

### License

This project is licensed under the MIT License. See `LICENSE` for more information.

## openaicheck.py *(written by OpenAI)

`openaicheck.py` is a script designed to inspect and validate the structure of a dataset for chat completions. It performs the following operations:
1. **Data Inspection**: The script initially loads the dataset from `output.jsonl` and prints the number of examples and the first example to provide an overview.
2. **Format Error Checks**: The script checks for various formatting issues such as:
   - Incorrect data types
   - Missing message lists
   - Unrecognized message keys
   - Missing content
   - Unrecognized roles in messages
   - Absence of an assistant's message
3. **Token Count**: It calculates the number of tokens for each message and provides distribution statistics such as:
   - Range (Min and Max)
   - Average (Mean)
   - Middle Value (Median)
   - 5th Percentile
   - 95th Percentile

### Understanding the Output

- **Number of Messages per Example Distribution**: Provides statistics about the number of messages in each example.
- **Total Tokens per Example Distribution**: Indicates the total number of tokens in each example.
- **Assistant Tokens per Example Distribution**: Pertains to the number of tokens in the assistant's messages within each example.
For each distribution, the following statistics are provided:
- **Range**: The smallest and largest values.
- **Average (Mean)**: The average value.
- **Middle Value (Median)**: The middle value when sorted.
- **5th Percentile**: 5% of the data lies below this value.
- **95th Percentile**: 95% of the data lies below this value.

[OpenAI Blog: GPT-3.5 Turbo, Fine-Tuning, and API Updates](https://openai.com/blog/gpt-3-5-turbo-fine-tuning-and-api-updates)

[OpenAI Fine-Tuning guide](https://platform.openai.com/docs/guides/fine-tuning)

### Authors
MIT License

(c) 2023 Ray Bernard 

This is a simple guide to get started with the fine-tune OpenAI Chat model. Please, do not hesitate to open an issue if you encounter any problem or have a suggestion.
