import { TextEmbedding } from "../types/file";
import { getEmbeddingsForText } from "./getEmbeddingsForText";

export type Embeddings = {
  meanEmbedding: number[];
  chunks: TextEmbedding[];
};

export async function createEmbeddings({
  text,
  maxCharLength,
}: {
  text: string;
  maxCharLength?: number;
}): Promise<Embeddings> {
  try {
    const textEmbeddings = await getEmbeddingsForText({
      text,
      maxCharLength,
    });

    // If there are 0 or 1 embeddings, the mean embedding is the same as the embedding
    if (textEmbeddings.length <= 1) {
      return {
        meanEmbedding: textEmbeddings[0]?.embedding ?? [],
        chunks: textEmbeddings,
      };
    }

    // If there are multiple embeddings, calculate their average
    const embeddingLength = textEmbeddings[0].embedding.length;
    const meanEmbedding = [];
    for (let i = 0; i < embeddingLength; i++) {
      // Sum up the values at the same index of each embedding
      let sum = 0;
      for (const textEmbedding of textEmbeddings) {
        sum += textEmbedding.embedding[i];
      }
      // Divide by the number of embeddings to get the mean
      meanEmbedding.push(sum / textEmbeddings.length);
    }

    return {
      meanEmbedding,
      chunks: textEmbeddings,
    };
  } catch (error: any) {
    console.log("Error: ", error);
    return {
      meanEmbedding: [],
      chunks: [],
    };
  }
}
