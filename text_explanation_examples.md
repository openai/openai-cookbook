# Text explanation examples

Large language models are useful for distilling information from long texts. Applications include:

* Answering questions about a piece of text, e.g.:
  * Querying a knowledge base to help people look up things they don't know
  * Querying an unfamiliar document to understand what it contains
  * Querying a document with structured questions in order to extract tags, classes, entities, etc.
* Summarizing text, e.g.:
  * Summarizing long documents
  * Summarizing back-and-forth emails or message threads
  * Summarizing detailed meeting notes with key points and next steps
* Classifying text, e.g.:
  * Classifying customer feedback messages by topic or type
  * Classifying documents by topic or type
  * Classifying the tone or sentiment of text
* Extracting entities, e.g.:
  * Extracting contact information from a customer message
  * Extracting names of people or companies or products from a document
  * Extracting things mentioned in customer reviews or feedback

Below are some simple examples of each.

## Answering questions about a piece of text

Here's an example prompt for answering questions about a piece of text:

```text
Using the following text, answer the following question. If the answer is not contained within the text, say "I don't know."

Text:
"""
Oklo Mine (sometimes Oklo Reactor or Oklo Mines), located in Oklo, Gabon on the west coast of Central Africa, is believed to be the only natural nuclear fission reactor. Oklo consists of 16 sites at which self-sustaining nuclear fission reactions are thought to have taken place approximately 1.7 billion years ago, and ran for hundreds of thousands of years. It is estimated to have averaged under 100 kW of thermal power during that time.
"""

Question: How many natural fission reactors have ever been discovered?

Answer:
```

[Output](https://beta.openai.com/playground/p/c8ZL7ioqKK7zxrMT2T9Md3gJ):

```text
 One. Oklo Mine is believed to be the only natural nuclear fission reactor.
```

If the text you wish to ask about is longer than the token limit (~4,000 tokens for `text-davinci-002`/`-003` and ~2,000 tokens for earlier models), you can split the text into smaller pieces, rank them by relevance, and then ask your question only using the most-relevant-looking pieces. This is demonstrated in [Question_answering_using_embeddings.ipynb](examples/Question_answering_using_embeddings.ipynb).

In the same way that students do better on tests when allowed to access notes, GPT-3 does better at answering questions when it's given text containing the answer.
Without notes, GPT-3 has to rely on its own long-term memory (i.e., internal weights), which are more prone to result in confabulated or hallucinated answers.

## Summarization

Here's a simple example prompt to summarize a piece of text:

```text
Summarize the following text.

Text:
"""
Two independent experiments reported their results this morning at CERN, Europe's high-energy physics laboratory near Geneva in Switzerland. Both show convincing evidence of a new boson particle weighing around 125 gigaelectronvolts, which so far fits predictions of the Higgs previously made by theoretical physicists.

"As a layman I would say: 'I think we have it'. Would you agree?" Rolf-Dieter Heuer, CERN's director-general, asked the packed auditorium. The physicists assembled there burst into applause.
"""

Summary:
```

[Output](https://beta.openai.com/playground/p/pew7DNB908TkUYiF0ZOdaIGc):

```text
CERN's director-general asked a packed auditorium if they agreed that two independent experiments had found convincing evidence of a new boson particle that fits predictions of the Higgs, to which the physicists assembled there responded with applause.
```

The triple quotation marks `"""` used in these example prompts aren't special; GPT-3 can recognize most delimiters, including `<>`, `{}`, or `###`. For long pieces of text, we recommend using some kind of delimiter to help disambiguate where one section of text ends and the next begins.

## Classification

If you want to classify the text, the best approach depends on whether the classes are known in advance.

If your classes _`are`_ known in advance, classification is often best done with a fine-tuned model, as demonstrated in [Fine-tuned_classification.ipynb](examples/Fine-tuned_classification.ipynb).

If your classes _`are not`_ known in advance (e.g., they are set by a user or generated on the fly), you can try zero-shot classification by either giving an instruction containing the classes or even by using embeddings to see which class label (or other classified texts) is most similar to the text (as demonstrated in [Zero-shot_classification.ipynb](examples/Zero-shot_classification_with_embeddings.ipynb)).

## Entity extraction

Here's an example prompt for entity extraction:

```text
From the text below, extract the following entities in the following format:
Companies: <comma-separated list of companies mentioned>
People & titles: <comma-separated list of people mentioned (with their titles or roles appended in parentheses)>

Text:
"""
In March 1981, United States v. AT&T came to trial under Assistant Attorney General William Baxter. AT&T chairman Charles L. Brown thought the company would be gutted. He realized that AT&T would lose and, in December 1981, resumed negotiations with the Justice Department. Reaching an agreement less than a month later, Brown agreed to divestiture—the best and only realistic alternative. AT&T's decision allowed it to retain its research and manufacturing arms. The decree, titled the Modification of Final Judgment, was an adjustment of the Consent Decree of 14 January 1956. Judge Harold H. Greene was given the authority over the modified decree....

In 1982, the U.S. government announced that AT&T would cease to exist as a monopolistic entity. On 1 January 1984, it was split into seven smaller regional companies, Bell South, Bell Atlantic, NYNEX, American Information Technologies, Southwestern Bell, US West, and Pacific Telesis, to handle regional phone services in the U.S. AT&T retains control of its long distance services, but was no longer protected from competition.
"""
```

[Output](https://beta.openai.com/playground/p/of47T7N5CtHF4RlvwFkTu3pN):

```text

Companies: AT&T, Bell South, Bell Atlantic, NYNEX, American Information Technologies, Southwestern Bell, US West, Pacific Telesis
People & titles: William Baxter (Assistant Attorney General), Charles L. Brown (AT&T chairman), Harold H. Greene (Judge)
```