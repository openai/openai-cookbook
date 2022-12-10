# OpenAI Cookbook

This repository shares example code and example prompts for accomplishing common tasks with the [OpenAI API].

To try these examples yourself, you’ll need an OpenAI account. [Create a free account to get started.][API Signup]

Most code examples are written in Python, though the concepts can be applied in any language.

In the same way that a cookbook's recipes don't span all possible meals or techniques, these examples don't span all possible use cases or methods. Use them as starting points upon which to elaborate, discover, and invent.

## Related resources

Beyond the code examples here, you can also learn about the [OpenAI API] from the following resources:

* Try out GPT-3 in the [OpenAI Playground]
* Read about the API in the [OpenAI Documentation]
* Discuss the API in the [OpenAI Community Forum]
* Look for help in the [OpenAI Help Center]
* See example prompts in the [OpenAI Examples]

## Examples, organized by capability

<table id="verticalalign">
<thead>
  <tr>
    <th></th>
    <th>Text</th>
    <th>Code</th>
  </tr>
</thead>
<tbody>
  <tr>
    <td>Write</td>
    <td>
        <li><a href='#1-write-text'>Copywriting</a></li>
        <li><a href='#1-write-text'>Blog posts</a></li>
        <li><a href='#1-write-text'>Product descriptions</a></li>
        <li><a href='#1-write-text'>Question generation</a></li>
    </td>
    <td>
        <li><a href='#1-write-code'>Code completion (e.g., GitHub Copilot)</a></li>
        <li><a href='#1-write-code'>Natural language software interfaces</a></li>
        <li><a href='#1-write-code'>Text to code</a></li>
        <li><a href='#1-write-code'>Unit tests</a></li>
    </td>
  </tr>
  <tr>
    <td>Explain</td>
    <td>
        <li><a href='#answering-questions-about-a-piece-of-text'>Q&A about a doc</a></li>
        <li><a href='#entity-extraction'>Entity extraction</a></li>
        <li><a href='#summarization'>Summarization</a></li>
        <li><a href='#classification'>Classification</a></li>
    </td>
    <td>
        <li><a href='#2-explain-code'>Code documentation</a></li>
        <li><a href='#2-explain-code'>Code explanation</a></li>
        <li><a href='#2-explain-code'>Docstrings</a></li>
    </td>
  </tr>
  <tr>
    <td>Edit</td>
    <td>
        <li><a href='#3-edit-text'>Editing</a></li>
        <li><a href='#translation'>Translation</a></li>
    </td>
    <td>
        <li><a href='#3-edit-code'>Conversion between languages or styles</a></li>
        <li><a href='#3-edit-code'>Bug fixing</a></li>
    </td>
  </tr>
  <tr>
    <td>Compare</td>
    <td>
        <li><a href='#semantic-search'>Semantic search</a></li>
        <li><a href='#recommendations'>Recommendations</a></li>
        <li><a href='#4-compare-text'>Clustering</a></li>
        <li><a href='#4-compare-text'>Near-duplicate detection</a></li>
    </td>
    <td>
        <li><a href='#4-compare-code'>Code search</a></li>
        <li><a href='#4-compare-code'>Code clustering</a></li>
    </td>
  </tr>
</tbody>
</table>

## How large language models work

[Large language models][Large language models Blog Post] are functions that map text to text. Given an input string of text, a large language model tries to predict the text that will come next.

The magic of large language models is that by being trained to minimize this prediction error over vast quantities of text, the models end up learning concepts useful for these predictions. For example, they learn concepts like:

* how to spell
* how grammar works
* how to paraphrase
* how to answer questions
* how to hold a conversation
* how to write in many languages
* how to code
* etc.

None of these capabilities are explicitly programmed in - they all emerge as a result of training.

GPT-3's capabilities now power [hundreds of different software products][GPT3 Apps Blog Post], including productivity apps, education apps, games, and more.

## How to control a large language model

Of all the inputs to a large language model, by far the most influential is the text prompt.

Large language models can be prompted to produce output in a few ways:

* **Instruction**: Tell the model what you want
* **Completion**: Induce the model to complete the beginning of what you want
* **Demonstration**: Show the model what you want, with either:
  * A few examples in the prompt
  * Many hundreds or thousands of examples in a fine-tuning training dataset

An example of each is shown below.

### Instruction prompts

Instruction-following models (e.g., `text-davinci-003` or any model beginning with `text-`) are specially designed to follow instructions. Write your instruction at the top of the prompt (or at the bottom, or both), and the model will do its best to follow the instruction and then stop. Instructions can be detailed, so don't be afraid to write a paragraph explicitly detailing the output you want.

Example instruction prompt:

```text
Extract the name of the author from the quotation below.

“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation
```

Output:

```text
Ted Chiang
```

### Completion prompt example

Completion-style prompts take advantage of how large language models try to write text they think is mostly likely to come next. To steer the model, try beginning a pattern or sentence that will be completed by the output you want to see. Relative to direct instructions, this mode of steering large language models can take more care and experimentation. In addition, the models won't necessarily know where to stop, so you will often need stop sequences or post-processing to cut off text generated beyond the desired output.

Example completion prompt:

```text
“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation

The author of this quote is
```

Output:

```text
 Ted Chiang
```

### Demonstration prompt example (few-shot learning)

Similar to completion-style prompts, demonstrations can show the model what you want it to do. This approach is sometimes called few-shot learning, as the model learns from a few examples provided in the prompt.

Example demonstration prompt:

```text
Quote:
“When the reasoning mind is forced to confront the impossible again and again, it has no choice but to adapt.”
― N.K. Jemisin, The Fifth Season
Author: N.K. Jemisin

Quote:
“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation
Author:
```

Output:

```text
 Ted Chiang
```

### Fine-tuned prompt example

With enough training examples, you can [fine-tune][Fine Tuning Docs] a custom model. In this case, instructions become unnecessary, as the model can learn the task from the training data provided. However, it can be helpful to include separator sequences (e.g., `->` or `###` or any string that doesn't commonly appear in your inputs) to tell the model when the prompt has ended and the output should begin. Without separator sequences, there is a risk that the model continues elaborating on the input text rather than starting on the answer you want to see.

Example fine-tuned prompt (for a model that has been custom trained on similar prompt-completion pairs):

```text
“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation

###


```

Output:

```text
 Ted Chiang
```

### More prompt advice

For more prompt examples, visit [OpenAI Examples][OpenAI Examples].

In general, the input prompt is the best lever for improving model outputs. You can try tricks like:

* **Give more explicit instructions.** E.g., if you want the output to be a comma separated list, ask it to return a comma separated list. If you want it to say "I don't know" when the it doesn't know the answer, tell it 'Say "I don't know" if you do not know the answer.'
* **Supply better examples.** If you're demonstrating examples in your prompt, make sure that your examples are diverse and high quality.
* **Ask the model to answer as if it was an expert.** Explicitly asking the model to produce high quality output or output as if it was written by an expert can induce the model to give higher quality answers that it thinks an expert would write. E.g., "The following answer is correct, high-quality, and written by an expert."
* **Prompt the model to write down the series of steps explaining its reasoning.** E.g., prepend your answer with something like "[Let's think step by step](https://arxiv.org/pdf/2205.11916v1.pdf)." Prompting the model to give an explanation of its reasoning before its final answer can increase the likelihood that its final answer is consistent and correct.

## Text Capabilities

### 1. Write text

Large language models are excellent at writing text. They can assist with:

* Blog posts
* Email copy
* Ad copy
* Website copy
* Product descriptions
* Memos
* Storytelling
* Brainstorming
* Question generation
* etc.

An example prompt for an instruction-following model:

```text
Write an email to a colleague named Jill congratulating her on her promotion. The tone should be warm yet professional. Mention how you admire the work she's been putting in.  Include a joke about how her pet lizard Max enjoys eating grasshoppers. Mention how you're looking forward to the team off-site next week.
```

Output:

```text
Dear Jill,

Congratulations on your promotion! I've been admiring the great work you've been putting in and I'm really happy for your success. Max the lizard must be thrilled too - I bet he's looking forward to feasting on even more grasshoppers!

I'm really looking forward to next week's team off-site. It's going to be great to catch up with everyone and brainstorm some new ideas.

Best,

[Your Name]
```

In general, writing can work with any style of prompt. Experiment to see what works best for your use case.

|                                                            | Advantages                                                                    | Disadvantages                                                                    |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Instruction-following models<br>(e.g., `text-davinci-003`) | Easiest to use                                                                | Less creative; less diverse; harder to control tone, length, etc.                |
| Base models<br>(e.g., `davinci`)                           | More creative                                                                 | More expensive (as including examples demonstrations in prompt will cost tokens) |
| Fine-tuned models                                          | Can train off of many examples; cheaper than including examples in the prompt | Hard to gather training data; training makes iteration slower and more expensive |

### 2. Explain text

One capability of large language models is distilling information from a piece of text. This can include:

* Answering questions about a piece of text, e.g.:
  * Querying an knowledge base to help people look up things they don't know
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

#### Answering questions about a piece of text

Example prompt for answering questions about a piece of text:

```text
Using the following text, answer the following question. If the answer is not contained within the text, say "I don't know."

Text:
"""
Oklo Mine (sometimes Oklo Reactor or Oklo Mines), located in Oklo, Gabon on the west coast of Central Africa, is believed to be the only natural nuclear fission reactor. Oklo consists of 16 sites at which self-sustaining nuclear fission reactions are thought to have taken place approximately 1.7 billion years ago, and ran for hundreds of thousands of years. It is estimated to have averaged under 100 kW of thermal power during that time.
"""

Question: How many natural fission reactors have ever been discovered?

Answer:
```

Output:

```text
 One
 ```

If the text you wish to ask about is longer than the token limit (~4,000 tokens for `text-davinci-003` and ~2,000 tokens for earlier models), we recommending splitting the text into smaller pieces, ranking them by relevance, and then asking the most-relevant-looking pieces.

#### Summarization

An example prompt for summarization:

```text
Summarize the following text.

Text:
"""
Two independent experiments reported their results this morning at CERN, Europe's high-energy physics laboratory near Geneva in Switzerland. Both show convincing evidence of a new boson particle weighing around 125 gigaelectronvolts, which so far fits predictions of the Higgs previously made by theoretical physicists.

"As a layman I would say: 'I think we have it'. Would you agree?" Rolf-Dieter Heuer, CERN's director-general, asked the packed auditorium. The physicists assembled there burst into applause.
"""

Summary:
```

Output:

```text
CERN has announced the discovery of a new particle, the Higgs boson. This particle has been predicted by theoretical physicists and is a major step forward in our understanding of the universe.
```

#### Classification

The best approach for classifying text depends on whether the classes are known in advance or not.

If your classes are known in advance, classification is best done with a fine-tuned model, as demonstrated in [Fine-tuned_classification.ipynb](examples/Fine-tuned_classification.ipynb).

If your classes are not known in advance (e.g., they are set by a user or generated on the fly), you can try zero-shot classification by either giving an instruction containing the classes or even by using embeddings to see which class label (or other classified texts) are most similar to the text ([Zero-shot_classification.ipynb](examples/Zero-shot_classification_with_embeddings.ipynb)).

#### Entity extraction

An example prompt for entity extraction:

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

Output:

```text
Companies: United States v. AT&T, AT&T, Justice Department, Bell South, Bell Atlantic, NYNEX, American Information Technologies, Southwestern Bell, US West, Pacific Telesis
People & titles: William Baxter (Assistant Attorney General), Charles L. Brown (AT&T chairman), Harold H. Greene (Judge)
```

### 3. Edit text

In addition to the [completion API endpoint][Completion API Docs], OpenAI now offers an [edit API endpoint][Edit API Docs] ([blog post][GPT3 Edit Blog Post]). In contrast to completions, which only take a single text input, edits take two text inputs: the instruction and the text to be modified.

An example edit prompt:

Instruction input:

```text
Fix the OCR errors
```

Text input:

```text
Therewassomehostilityntheenergybehindthe researchreportedinPerceptrons....Part of ourdrivecame,aswequiteplainlyacknoweldgednourbook,fromhe facthatfundingndresearchnergywerebeingdissipatedon. . .misleadingttemptsouseconnectionistmethodsnpracticalappli-cations.
```

Output:

```text
There was some hostility in the energy behind the research reported in Perceptrons....Part of our drive came, as we quite plainly acknowledged in our book, from the fact that funding and research energy were being dissipated on...misleading attempts to use connectionist methods in practical applications.
```

#### Translation

Translation is another emergent capability of large language models. In 2021, [GPT-3 was used](https://arxiv.org/abs/2110.05448) to set a new state-of-the-art record in unsupervised translation on the WMT14 English-French benchmark.

Example translation prompt using the edits endpoint:

Instruction input:

```text
translation into French
```

Text input:

```text
That's life.
```

Output:

```text
C'est la vie.
```

Example translation prompt using the completions endpoint:

```text
Translate the following text from English to French.

English: That's life.
French:
```

Output:

```text
 C'est la vie.
```

Tips for translation:

* Performance is best on the most common languages
* We've seen better performance when the instruction is given in the final language (so if translating into French, give the instruction `Traduire le texte de l'anglais au français.` rather than `Translate the following text from English to French.`)
* Backtranslation (as described [here](https://arxiv.org/abs/2110.05448)) can also increase performance
* Text with colons and heavy punctuation can trip up the instruction-following models, especially if the instruction is using colons (e.g., `English: {english text} French:`)
* The edits endpoint has been seen to sometimes repeat the text input alongside the translation

When it comes to translation, large language models particularly shine at combining other instructions alongside translation. For example, you can ask GPT-3 to translate Slovenian to English but keep all LaTeX typesetting commands unchanged. The following notebook details how we translated a Slovenian math book into English:

[Translation of a Slovenian math book into English](examples/book_translation/translate_latex_book.ipynb)

### 4. Compare text

The [OpenAI API embeddings endpoint][Embeddings Docs] can be used to measure similarity between pieces of text ([blog post][Embeddings Blog Post]). By leveraging GPT-3's understanding of text, these embeddings [achieved state-of-the-art results](https://arxiv.org/abs/2201.10005) on benchmarks in both unsupervised learning and transfer learning settings.

Embeddings can be used for semantic search, recommendations, cluster analysis, near-duplicate detection, and more.

#### Semantic search

Embeddings can be used for search either by themselves or as a feature in a larger system.

The simplest way to use embeddings for search is as follows:

* Before the search (precompute):
  * Split your text corpus into chunks smaller than the token limit (e.g., ~2,000 tokens)
  * Embed each chunk using a 'doc' model (e.g., `text-search-curie-doc-001`)
  * Store those embeddings in your own database or in a vector search provider like [Pinecone](https://www.pinecone.io) or [Weaviate](https://weaviate.io)
* At the time of the search (live compute):
  * Embed the search query using the corresponding 'query' model (e.g. `text-search-curie-query-001`)
  * Find the closest embeddings in your database
  * Return the top results, ranked by cosine similarity

An example of how to use embeddings for search is shown in [Semantic_text_search_using_embeddings.ipynb](examples/Semantic_text_search_using_embeddings.ipynb).

In more advanced search systems, the the cosine similarity of embeddings can be used as one feature among many in ranking search results.

#### Recommendations

Recommendations are quite similar to search, except that instead of a free-form text query, the inputs are items in a set. And instead of using pairs of doc-query models, you can use a single symmetric similarity model (e.g., `text-similarity-curie-001`).

An example of how to use embeddings for recommendations is shown in [Recommendation_using_embeddings.ipynb](examples/Recommendation_using_embeddings.ipynb).

Similar to search, these cosine similarity scores can either be used on their own to rank items or as features in larger ranking algorithms.

#### Customizing Embeddings

Although OpenAI's embedding model weights cannot be fine-tuned, you can still use training data to customize embeddings to your application.

In the following notebook, we provide an example method for customizing your embeddings using training data. The idea of the method is to train a custom matrix to multiply embedding vectors by in order to get new customized embeddings. With good training data, this custom matrix will highlight the features relevant to your training labels and suppress the rest. You can equivalently consider the matrix multiplication as (a) a modification of the embeddings or (b) a modification of the distance function used to measure the distances between embeddings.

* [Customizing_embeddings.ipynb](examples/Customizing_embeddings.ipynb)

## Code Capabilities

Large language models aren't only great at text - they can be great at code too. OpenAI's specialized code model is called [Codex].

Codex powers [more than 70 products][Codex Apps Blog Post], including:

* [GitHub Copilot] (autocompletes code in VS Code and other IDEs)
* [Pygma](https://pygma.app/) (turns Figma designs into code)
* [Replit](https://replit.com/) (has an 'Explain code' button and other features)
* [Warp](https://www.warp.dev/) (a smart terminal with AI command search)
* [Machinet](https://machinet.net/) (writes Java unit test templates)

Note that unlike instruction-following text models (e.g., `text-davinci-003`), Codex is *not* trained to follow instructions. As a result, designing good prompts can take more care.

### 1. Write code

An example prompt for writing code with `code-davinci-002`:

````text
SQL tables (and columns):
* Customers(customer_id, signup_date)
* Streaming(customer_id, video_id, watch_date, watch_minutes)

A well-written SQL query that lists customers who signed up during March 2020 and watched more than 50 hours of video in their first 30 days:
```
````

Output:

```sql
SELECT c.customer_id
FROM Customers c
JOIN Streaming s
ON c.customer_id = s.customer_id
WHERE c.signup_date BETWEEN '2020-03-01' AND '2020-03-31'
AND s.watch_date BETWEEN c.signup_date AND DATE_ADD(c.signup_date, INTERVAL 30 DAY)
GROUP BY c.customer_id
HAVING SUM(s.watch_minutes) > 50 * 60
```

`code-davinci-002` is able to make inferences from variable names; for example, it infers that `watch_minutes` has units of minutes and therefore needs to be converted by a factor of 60 before being compared with 50 hours.

### 2. Explain code

Code explanation can be applied to many use cases:

* Generating in-code documentation (e.g., Python docstrings, git commit messages)
* Generating out-of-code documentation (e.g., man pages)
* In an interactive code exploration tool
* Communicating program results back to users via a natural language interface

An example prompt for explaining code with `code-davinci-002`:

````text
A SQL query:
```
SELECT c.customer_id
FROM Customers c
JOIN Streaming s
ON c.customer_id = s.customer_id
WHERE c.signup_date BETWEEN '2020-03-01' AND '2020-03-31'
AND s.watch_date BETWEEN c.signup_date AND DATE_ADD(c.signup_date, INTERVAL 30 DAY)
GROUP BY c.customer_id
HAVING SUM(s.watch_minutes) > 50 * 60
```

Questions:
1. What does the SQL query do?
2. Why might someone be interested in this time period?
3. Why might a company be interested in this SQL query?

Answers:
````

Output:

```text
1. The SQL query finds all customers who signed up in March 2020 and watched more than 50 hours of content in the first 30 days after signing up.
2. The time period is interesting because it is the first month of the COVID-19 pandemic.
3. A company might be interested in this SQL query because it can help them understand how the pandemic has affected their business.
```

### 3. Edit code

OpenAI's edit endpoint is particularly useful for editing code.

Example text input to `code-davinci-edit-001`:

```python
def tribonacci(n):
    if n == 0:
        return 0
    elif n == 1:
        return 1
    elif n == 2:
        return 1
    elif n == 3:
        return 2
    else:
        return tribonacci(n-1) + tribonacci(n-2) + tribonacci(n-3)
```

Example instruction inputs:

```text
Add a docstring
```

```text
Add typing
```

```text
Improve the runtime
```

```text
Add a test
```

```text
Translate to JavaScript (or Rust or Lisp or any language you like)
```

Example output after improving the runtime and translating to JavaScript:

```JavaScript
function tribonacci(n) {
  let a = 0;
  let b = 1;
  let c = 1;
  for (let i = 0; i < n; i++) {
    [a, b, c] = [b, c, a + b + c];
  }
  return a;
}
```

As you can see, `code-davinci-edit-001` was able to successfully reduce the function's runtime from exponential down to linear, as well as convert from Python to JavaScript.

### 4. Compare code

The OpenAI API also features code search embeddings, which can measure the relevance of a section of code to a text query, or the similarity between two sections of code.

OpenAI code search embeddings significantly improved the state-of-the-art on the [CodeSearchNet] evaluation suite, scoring 93.5% versus the previous record of 77.4%.

Read more about OpenAI's code embeddings in the [blog post announcement][Embeddings Blog Post] or [documentation][Embeddings Docs].

Code embeddings can be useful for use cases such as:

* Code search
* Codebase clustering & analysis

An example of code search is shown in [Code_search.ipynb](examples/Code_search.ipynb).

We haven't written an example of code clustering, but the idea is the same as the text clustering in [Clustering.ipynb](examples/Clustering.ipynb).


[OpenAI API]: https://openai.com/api/
[Embeddings Docs]: https://beta.openai.com/docs/guides/embeddings
[Edit API Docs]: https://beta.openai.com/docs/api-reference/edits
[Completion API Docs]: https://beta.openai.com/docs/api-reference/completions
[Fine Tuning Docs]: https://beta.openai.com/docs/guides/fine-tuning
[CodeSearchNet]: https://github.com/github/CodeSearchNet
[Embeddings Blog Post]: https://openai.com/blog/introducing-text-and-code-embeddings/
[Codex Apps Blog Post]: https://openai.com/blog/codex-apps/
[GPT3 Edit Blog Post]: https://openai.com/blog/gpt-3-edit-insert/
[Large language models Blog Post]: https://openai.com/blog/better-language-models/
[GitHub Copilot]: https://copilot.github.com/
[Codex]: https://openai.com/blog/openai-codex/
[API Signup]: https://beta.openai.com/signup
[GPT3 Apps Blog Post]: https://openai.com/blog/gpt-3-apps/
[OpenAI Playground]: https://beta.openai.com/playground
[OpenAI Documentation]: https://beta.openai.com/docs/introduction
[OpenAI Community Forum]: https://community.openai.com/top?period=monthly
[OpenAI Help Center]: https://help.openai.com/en/
[OpenAI Examples]: https://beta.openai.com/examples
