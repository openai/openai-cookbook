import { FileLite, FileChunk } from "../types/file";
import { embedding } from "./openai";

// This is the minimum cosine similarity score that a file must have with the search query to be considered relevant
// This is an arbitrary value, and you should vary/ remove this depending on the diversity of your dataset
const COSINE_SIM_THRESHOLD = 0.72;

// This function takes a search query and a list of files, and returns the chunks of text that are most semantically similar to the query
export async function searchFileChunks({
  searchQuery,
  files,
  maxResults,
}: {
  searchQuery: string;
  files: FileLite[];
  maxResults: number;
}): Promise<FileChunk[]> {
  // Get the search query embedding
  const searchQueryEmbeddingResponse = await embedding({
    input: searchQuery,
  });

  // Get the first element in the embedding array
  const searchQueryEmbedding =
    searchQueryEmbeddingResponse.length > 0
      ? searchQueryEmbeddingResponse[0]
      : [];

  // Rank the chunks by their cosine similarity to the search query (using dot product since the embeddings are normalized) and return this
  const rankedChunks = files
    // Map each file to an array of chunks with the file name and score
    .flatMap((file) =>
      file.chunks
        ? file.chunks.map((chunk) => {
            // Calculate the dot product between the chunk embedding and the search query embedding
            const dotProduct = chunk.embedding.reduce(
              (sum, val, i) => sum + val * searchQueryEmbedding[i],
              0
            );
            // Assign the dot product as the score for the chunk
            return { ...chunk, filename: file.name, score: dotProduct };
          })
        : []
    )
    // Sort the chunks by their scores in descending order
    .sort((a, b) => b.score - a.score)
    // Filter the chunks by their score above the threshold
    .filter((chunk) => chunk.score > COSINE_SIM_THRESHOLD)
    // Take the first maxResults chunks
    .slice(0, maxResults);

  return rankedChunks;
}
