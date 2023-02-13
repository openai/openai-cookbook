import { IncomingMessage } from "http";
import {
  Configuration,
  CreateCompletionRequest,
  CreateCompletionResponse,
  OpenAIApi,
} from "openai";

// This file contains utility functions for interacting with the OpenAI API

if (!process.env.OPENAI_API_KEY) {
  throw new Error("Missing OPENAI_API_KEY environment variable");
}

const configuration = new Configuration({
  apiKey: process.env.OPENAI_API_KEY,
});
export const openai = new OpenAIApi(configuration);

type CompletionOptions = Partial<CreateCompletionRequest> & {
  prompt: string;
  fallback?: string;
};

type EmbeddingOptions = {
  input: string | string[];
  model?: string;
};

export async function completion({
  prompt,
  fallback,
  max_tokens = 800,
  temperature = 0,
  model = "text-davinci-003",
  ...otherOptions
}: CompletionOptions) {
  try {
    const result = await openai.createCompletion({
      prompt,
      max_tokens,
      temperature,
      model,
      ...otherOptions,
    });

    if (!result.data.choices[0].text) {
      throw new Error("No text returned from the completions endpoint.");
    }
    return result.data.choices[0].text;
  } catch (error) {
    if (fallback) return fallback;
    else throw error;
  }
}

export async function* completionStream({
  prompt,
  fallback,
  max_tokens = 800,
  temperature = 0,
  model = "text-davinci-003",
}: CompletionOptions) {
  try {
    const result = await openai.createCompletion(
      {
        prompt,
        max_tokens,
        temperature,
        model,
        stream: true,
      },
      { responseType: "stream" }
    );

    const stream = result.data as any as IncomingMessage;

    for await (const chunk of stream) {
      const line = chunk.toString().trim();
      const message = line.split("data: ")[1];

      if (message === "[DONE]") {
        break;
      }

      const data = JSON.parse(message) as CreateCompletionResponse;

      yield data.choices[0].text;
    }
  } catch (error) {
    if (fallback) yield fallback;
    else throw error;
  }
}

export async function embedding({
  input,
  model = "text-embedding-ada-002",
}: EmbeddingOptions): Promise<number[][]> {
  const result = await openai.createEmbedding({
    model,
    input,
  });

  if (!result.data.data[0].embedding) {
    throw new Error("No embedding returned from the completions endpoint");
  }

  // Otherwise, return the embeddings
  return result.data.data.map((d) => d.embedding);
}
