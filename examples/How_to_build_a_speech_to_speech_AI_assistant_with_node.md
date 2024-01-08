# How to build a voice assistant with Node.js

![Slide 1](../images/speech_to_speech_slide_4.png)

This article will teach you how to build a speech-to-speech AI assistant using OpenAI's Node.js SDK. We will convert a user's audio prompt into text with Whisper, then send that prompt to ChatGPT-4. When we receive a response, we'll convert it back into audio using text-to-speech (TTS).

To supplement this article I have created an [interactive screencast](https://scrimba.com/scrim/cZ2QLwTG) to walk you through the steps. If you feel the need for a primer on the OpenAI API as you progress through this guide, I would recommend reading [OpenAI's quickstart tutorial](https://platform.openai.com/docs/quickstart?context=node) or watching [this free Scrimba course.](https://scrimba.com/learn/introtoaiengineering)

<ScrimPlayer scrimId="cZ2QLwTG" />

## Setting up our dependencies and authenticating with OpenAI
First, we need to install our dependencies:

- `import OpenAI from 'openai';`
- `import fs from "fs";`

Now we make our connection to the OpenAI API server, using our API key. If you're watching the [scrim](https://scrimba.com/scrim/cZ2QLwTG) above, you can store your API key in the environment variables for the browser environment by following the steps in [this article](https://different-marmoset-f7b.notion.site/How-to-set-environment-variables-in-Scrimba-f8edc638005a4e97b557c6ab1752248a).

```
const openai = new OpenAI({
    apiKey: process.env.OPENAI_API_KEY
});
```

## Transcribe user audio prompt

![Slide 2](../images/speech_to_speech_slide_1.png)

First, we will demonstrate how to turn spoken word audio into text using the Whisper model.  The API endpoint `openai.audio.transcriptions.create` accepts up to six [request body attributes](https://platform.openai.com/docs/api-reference/audio/createTranscription):

#### ___Required___
- file
- model

#### ___Optional___
- language
- prompt
- response_format
- temperature

Using our OpenAI API connection, we can send our audio to the Whisper model to transcribe the audio into text. We will send a request to the `transcriptions` endpoint, but first we have to create a read stream for the audio file using `fs.createReadStream` so that we can send that audio file to the API.

```
const audioData = await fs.createReadStream(audioFilePath);
const transcription = await openai.audio.transcriptions.create({
    model: "whisper-1", 
    file: audioData,
    language: "en" // ISO-639-1 format
});
```

It will respond with a simple object that looks like this:

```
// transcription
{ text: 'Where is the Getty Museum located?' }
```

As an aside, we can also use the same API endpoint to translate our audio to another language by changing the `language` attribute in our request body to reflect the language we intend to translate to:

```
const transcription = await openai.audio.transcriptions.create({
    model: "whisper-1", 
    file: audioData,
    language: "fr" // ISO-639-1 format
});
```

This will translate our audio to French, but you can use any language in ISO-639-1 format:

```
// transcription
{ text: 'Où se trouve le musée du Getty?' }
```

## Sending the transcription to ChatGPT 4

![Slide 3](../images/speech_to_speech_slide_2.png)

In the next step we will be sending the transcription text we just received from `openai.audio.transcriptions.create` to the `openai.chat.completions.create` endpoint. There are many [request body attributes](https://platform.openai.com/docs/api-reference/chat/create) for the `openai.chat.completions.create` endpoint, but here are a few important attributes:

#### ___Required___

- messages
- model

#### ___Optional___

- max_tokens
- response_format
- tools

A Note on `role` within our request body `messages` attribute:

```
messages: [
        {"role": "system", "content": "You are a helpful assistant that gives short succinct replies."},
        {"role": "user", "content": question}
    ]
``` 

Roles are a way to guide the model’s responses. Commonly used roles include “system,” “user,” and “assistant.” The “system” provides high-level instructions, the “user” presents queries or prompts, and the “assistant” is the model’s response. Using roles strategically can significantly improve the model's output.

**System Role:** Set clear context for the system. Begin with a system message to define the context or behavior you desire from the model. This acts as a guidepost for subsequent interactions. Notice that we instructed the system to be "succinct" in its description, to keep the response length shorter.

**User Role:** Make explicit/direct user prompts. Being clear and concise in the user role ensures the model grasps the exact requirement, leading to more accurate responses.

Our request body for the `openai.chat.completions.create` endpoint will look something like the following:

```
// transcription = { text: 'Where is the Getty Museum located?' }
const question = transcription.text 
const completion = await openai.chat.completions.create({
    messages: [
        {"role": "system", "content": "You are a helpful assistant that gives short succint replies."},
        {"role": "user", "content": question}
    ],
    model: "gpt-4-1106-preview"
});
```

## Taking a look at the ChatGPT 4 response

The completion object we receive from ChatGPT 4 will look something like this:

```
{
    id: "chatcmpl-8VudWT5n7Wpnmmnc4cCFkrGDjrvmM", 
    object: "chat.completion", 
    created: 1702616570, 
    model: "gpt-4-1106-preview", 
    choices: [
        {
            index: 0, 
            message: {
                role: "assistant",
                content: "The Getty Museum comprises two locations: the Getty Center in Los Angeles and the Getty Villa in Pacific Palisades, California."
                }, 
            finish_reason: "stop"
        }
    ], 
    usage: {
        prompt_tokens: 30, 
        completion_tokens: 25, 
        total_tokens: 55
    }, 
    system_fingerprint: "fp_3677ac4g89"
}
```

Notice that the response has an attribute `finish_reason` that has a value of `"stop"`. This means that the response finished successfully. If you see `finish_reason: "length"`, that means that the response was cut short because it surpassed the maximum length. You may need to change your prompt to ask more explicitly for a more concise response.

## Create speech from response

![Slide 4](../images/speech_to_speech_slide_3.png)

Lastly, we will turn the ChatGPT 4 response into speech using the `openai.audio.speech.create` endpoint. Here are the [request body attributes](https://platform.openai.com/docs/api-reference/audio/createSpeech):

#### ___Required___

- model
- input
- voice

#### ___Optional___

- response_format
- speed

For real-time applications, the standard `tts-1` model provides the lowest latency but at a lower quality than the `tts-1-hd` model. Due to the way the audio is generated, `tts-1` is likely to generate content that has more static in certain situations than `tts-1-hd`.

If we study the completion object above, we can see that the part we need in this case is `completion.choices[0].message.content`. This portion of the completion object contains the assistant's response to our question. We will send this as the `input` value in our request body.

```
const mp3 = await openai.audio.speech.create({
    model: "tts-1",
    voice: "alloy",
    input: completion.choices[0].message.content,
});
```

Here we use the `openai.audio.speech.create` endpoint to send the text response we got back from ChatGPT 4 to the TTS model in order to receive an audio file back. Once we receive the audio file from the TTS model, we need to create a buffer for the file then write it locally to our machine.

```
const buffer = Buffer.from(await mp3.arrayBuffer());
await fs.promises.writeFile("./speech.mp3", buffer);
```

If everything worked properly, we should have our speech saved in an audio file called `speech.mp3`, where we can then handle it accordingly.

![Slide 1](../images/speech_to_speech_slide_4.png)

## Conclusion

Hopefully this gave you some ideas on how to use the OpenAI API. We could have made a loop that continuously asks a user for audio prompts, then responds in audio as well. We could also use this to create a translation application. Give it a try on your local computer and build it out into your next cool application. Good luck, and have fun!
