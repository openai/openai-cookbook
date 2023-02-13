// A function that takes a file name and a string and returns true if the file name is contained in the string
// after removing punctuation and whitespace from both
export const isFileNameInString = (fileName: string, str: string) => {
  // Convert both to lowercase and remove punctuation and whitespace
  const normalizedFileName = fileName
    .toLowerCase()
    .replace(/[.,/#!$%^&*;:{}=-_~()\s]/g, "");
  const normalizedStr = str
    .toLowerCase()
    .replace(/[.,/#!$%^&*;:{}=-_~()\s]/g, "");

  // Return true if the normalized file name is included in the normalized string
  return normalizedStr.includes(normalizedFileName);
};
