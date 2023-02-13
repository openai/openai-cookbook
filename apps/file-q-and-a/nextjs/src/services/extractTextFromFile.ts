import fs from "fs";
import mammoth from "mammoth";
import pdfParse from "pdf-parse";
import { NodeHtmlMarkdown } from "node-html-markdown";

export default async function extractTextFromFile({
  filepath,
  filetype,
}: {
  filepath: string;
  filetype: string;
}): Promise<string> {
  const buffer: Buffer = await new Promise((resolve, reject) => {
    const fileStream = fs.createReadStream(filepath);
    const chunks: any[] = [];
    fileStream.on("data", (chunk) => {
      chunks.push(chunk);
    });
    fileStream.on("error", (error) => {
      reject(error);
    });
    fileStream.on("end", () => {
      resolve(Buffer.concat(chunks));
    });
  });

  // Handle different file types using different modules
  switch (filetype) {
    case "application/pdf":
      const pdfData = await pdfParse(buffer);
      return pdfData.text;
    case "application/vnd.openxmlformats-officedocument.wordprocessingml.document": // i.e. docx file
      const docxResult = await mammoth.extractRawText({ path: filepath });
      return docxResult.value;
    case "text/markdown":
    case "text/csv":
    case "text/html":
      const html = buffer.toString();
      return NodeHtmlMarkdown.translate(html);
    case "text/plain":
      return buffer.toString();
    default:
      throw new Error("Unsupported file type");
  }
}
