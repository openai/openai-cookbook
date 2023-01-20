# Text editing examples

In addition to the [completions API endpoint][Completion API Docs], OpenAI offers an [edits API endpoint][Edit API Docs]. Read more at:

* [Blog post announcement (Mar 2022)][GPT3 Edit Blog Post]
* [Edit API documentation][Edit API Docs]

In contrast to completions, which only take a single text input, edits take two text inputs: the instruction and the text to be modified. For example:

Instruction input:

```text
Fix the OCR errors
```

Text input:

```text
Therewassomehostilityntheenergybehindthe researchreportedinPerceptrons....Part of ourdrivecame,aswequiteplainlyacknoweldgednourbook,fromhe facthatfundingndresearchnergywerebeingdissipatedon. . .misleadingttemptsouseconnectionistmethodsnpracticalappli-cations.
```

[Output](https://beta.openai.com/playground/p/5W5W6HHlHrGsLu1cpx0VF4qu):

```text
There was some hostility in the energy behind the research reported in Perceptrons....Part of our drive came, as we quite plainly acknowledged in our book, from the fact that funding and research energy were being dissipated on...misleading attempts to use connectionist methods in practical applications.
```

In general, instructions can be imperative, present tense, or past tense. Experiment to see what works best for your use case.

## Translation

One application of the edit API is translation.

Large language models are excellent at translating across common languages. In 2021, [GPT-3 set](https://arxiv.org/abs/2110.05448) a new state-of-the-art record in unsupervised translation on the WMT14 English-French benchmark.

Here's an example of how to translate text using the edits endpoint:

Instruction input:

```text
translation into French
```

Text input:

```text
That's life.
```

[Output](https://beta.openai.com/playground/p/6JWAH8a4ZbEafSDyRsSVdgKr):

```text
C'est la vie.
```

Of course, many tasks that can be accomplished with the edits endpoint can also be done by the completions endpoint too. For example, you can request a translate by prepending an instruction as follows:

```text
Translate the following text from English to French.

English: That's life.
French:
```

[Output](https://beta.openai.com/playground/p/UgaPfgjBNTRRPeNcMSNtGzcu):

```text
 C'est la vie.
```

Tips for translation:

* Performance is best on the most common languages
* We've seen better performance when the instruction is given in the final language (so if translating into French, give the instruction `Traduire le texte de l'anglais au français.` rather than `Translate the following text from English to French.`)
* Backtranslation (as described [here](https://arxiv.org/abs/2110.05448)) can also increase performance
* Text with colons and heavy punctuation can trip up the instruction-following models, especially if the instruction uses colons (e.g., `English: {english text} French:`)
* The edits endpoint sometimes repeats the original text input alongside the translation, which can be monitored and filtered

When it comes to translation, large language models particularly shine at combining other instructions alongside translation. For example, you can ask GPT-3 to translate Slovenian to English but keep all LaTeX typesetting commands unchanged. The following notebook details how we translated a Slovenian math book into English:

[Translation of a Slovenian math book into English](examples/book_translation/translate_latex_book.ipynb)


[Edit API Docs]: https://beta.openai.com/docs/api-reference/edits
[Completion API Docs]: https://beta.openai.com/docs/api-reference/completions
[GPT3 Edit Blog Post]: https://openai.com/blog/gpt-3-edit-insert/