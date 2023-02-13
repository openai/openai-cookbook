import { TextEmbedding } from "../types/file";
import { chunkText } from "./chunkText";
import { embedding } from "./openai";

// There isn't a good JS tokenizer at the moment, so we are using this approximation of 4 characters per token instead. This might break for some languages.
const MAX_CHAR_LENGTH = 250 * 4;

// This function takes a text and returns an array of embeddings for each chunk of the text
// The text is split into chunks of a given maximum charcter length
// The embeddings are computed in batches of a given size
export async function getEmbeddingsForText({
  text,
  maxCharLength = MAX_CHAR_LENGTH,
  batchSize = 20,
}: {
  text: string;
  maxCharLength?: number;
  batchSize?: number;
}): Promise<TextEmbedding[]> {
  const textChunks = chunkText({ text, maxCharLength });

  const batches = [];
  for (let i = 0; i < textChunks.length; i += batchSize) {
    batches.push(textChunks.slice(i, i + batchSize));
  }

  try {
    const batchPromises = batches.map((batch) => embedding({ input: batch }));

    const embeddings = (await Promise.all(batchPromises)).flat();

    const textEmbeddings = embeddings.map((embedding, index) => ({
      embedding,
      text: textChunks[index],
    }));

    return textEmbeddings;
  } catch (error: any) {
    console.log("Error: ", error);
    return [];
  }
}
