import type { NextApiRequest, NextApiResponse } from "next";

import { searchFileChunks } from "../../services/searchFileChunks";
import { FileChunk, FileLite } from "../../types/file";

type Data = {
  searchResults?: FileChunk[];
  error?: string;
};

export const config = {
  api: {
    bodyParser: {
      sizeLimit: "30mb",
    },
  },
};

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<Data>
) {
  try {
    const searchQuery = req.body.searchQuery as string;

    const files = req.body.files as FileLite[];

    const maxResults = req.body.maxResults as number;

    if (!searchQuery) {
      res.status(400).json({ error: "searchQuery must be a string" });
      return;
    }

    if (!Array.isArray(files) || files.length === 0) {
      res.status(400).json({ error: "files must be a non-empty array" });
      return;
    }

    if (!maxResults || maxResults < 1) {
      res
        .status(400)
        .json({ error: "maxResults must be a number greater than 0" });
      return;
    }

    const searchResults = await searchFileChunks({
      searchQuery,
      files,
      maxResults,
    });

    res.status(200).json({ searchResults });
  } catch (error) {
    console.error(error);

    res.status(500).json({ error: "Something went wrong" });
  }
}
