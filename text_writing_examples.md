# Text writing examples

Large language models are excellent at writing. They can assist with all sorts of tasks:

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

The easiest way to prompt GPT-3 is to tell it what you'd like. For example, if you want it to write an email, you could use a prompt like this:

```text
Write an email to a colleague named Jill congratulating her on her promotion. The tone should be warm yet professional. Mention how you admire the work she's been putting in.  Include a joke about how her pet lizard Max enjoys eating grasshoppers. Mention how you're looking forward to the team off-site next week.
```

[Output](https://beta.openai.com/playground/p/fUeh5saVLI2dhU0WU3nZtIiU):

```text
Subject: Congratulations on Your Promotion, Jill!

Dear Jill,

Congratulations on your promotion! I'm so proud of you and all the hard work you've been putting in. It's been inspiring to watch you grow in your career.

I'm sure Max the lizard is also celebrating with you. I hear he loves eating grasshoppers, so you should treat him to a special snack!

I'm looking forward to seeing you at the team off-site next week. I'm sure it will be a great opportunity to celebrate your success.

All the best,

[Your Name]
```

In general, writing can work with any style of prompt, whether it's an instruction or a series of examples to follow. Experiment to see what works best for your use case.

Writing also works with any type of model, though they each have strengths and weaknesses.

|                                                            | Advantages                                                                    | Disadvantages                                                                    |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Instruction-following models<br>(e.g., `text-davinci-003`) | Easiest to use                                                                | Less diverse; less creative; sometimes harder to steer tone, style, etc.                |
| Base models<br>(e.g., `davinci`)                           | Potentially more creative and diverse                                                                 | Harder to prompt well, more expensive (as examples in the prompt cost extra tokens) |
| Fine-tuned models                                          | Can train off of many examples; cheaper than including examples in the prompt | Hard to gather training data; training makes iteration slower and more expensive |
