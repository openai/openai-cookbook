export interface FileLite {
  expanded?: boolean;
  name: string;
  url?: string;
  type?: string;
  score?: number;
  size?: number;
  embedding?: number[]; // The file embedding -- or mean embedding if there are multiple embeddings for the file
  chunks?: TextEmbedding[]; // The chunks of text and their embeddings
  extractedText?: string; // The extracted text from the file
}

export interface FileChunk extends TextEmbedding {
  filename: string;
  score?: number;
}

export interface TextEmbedding {
  text: string;
  embedding: number[];
}
