import { IncomingMessage } from "http";
import {
  ChatCompletionRequestMessageRoleEnum,
  Configuration,
  CreateChatCompletionResponse,
  CreateCompletionRequest,
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
  max_tokens,
  temperature = 0,
  model = "gpt-3.5-turbo", // use gpt-4 for better results
}: CompletionOptions) {
  try {
    // Note: this is not the proper way to use the ChatGPT conversational format, but it works for now
    const messages = [
      {
        role: ChatCompletionRequestMessageRoleEnum.System,
        content: prompt ?? "",
      },
    ];

    const result = await openai.createChatCompletion({
      model,
      messages,
      temperature,
      max_tokens: max_tokens ?? 800,
    });

    if (!result.data.choices[0].message) {
      throw new Error("No text returned from completions endpoint");
    }
    return result.data.choices[0].message.content;
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
  model = "gpt-3.5-turbo", // use gpt-4 for better results
}: CompletionOptions) {
  try {
    // Note: this is not the proper way to use the ChatGPT conversational format, but it works for now
    const messages = [
      {
        role: ChatCompletionRequestMessageRoleEnum.System,
        content: prompt ?? "",
      },
    ];

    const result = await openai.createChatCompletion(
      {
        model,
        messages,
        temperature,
        max_tokens: max_tokens ?? 800,
        stream: true,
      },
      {
        responseType: "stream",
      }
    );
    const stream = result.data as any as IncomingMessage;

    let buffer = "";
    const textDecoder = new TextDecoder();

    for await (const chunk of stream) {
      buffer += textDecoder.decode(chunk, { stream: true });
      const lines = buffer.split("\n");

      // Check if the last line is complete
      if (buffer.endsWith("\n")) {
        buffer = "";
      } else {
        buffer = lines.pop() || "";
      }

      for (const line of lines) {
        const message = line.trim().split("data: ")[1];
        if (message === "[DONE]") {
          break;
        }

        // Check if the message is not undefined and a valid JSON string
        if (message) {
          try {
            const data = JSON.parse(message) as CreateChatCompletionResponse;
            // @ts-ignore
            if (data.choices[0].delta?.content) {
              // @ts-ignore
              yield data.choices[0].delta?.content;
            }
          } catch (error) {
            console.error("Error parsing JSON message:", error);
          }
        }
      }
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
