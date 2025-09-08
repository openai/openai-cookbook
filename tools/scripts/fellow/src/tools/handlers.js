import * as noteTools from "./contacts/index.js";
import * as recordingTools from "./meetings/index.js"; 
import * as transcriptTools from "./transcripts/index.js";
import * as userTools from "./users/index.js";

// Create a map of tool names to their handlers
const toolHandlers = new Map();

// Add note tool handlers (renamed from contacts)
for (const [toolName, tool] of Object.entries(noteTools)) {
  toolHandlers.set(tool.toolSchema.name, tool.handler);
}

// Add recording tool handlers (renamed from meetings)
for (const [toolName, tool] of Object.entries(recordingTools)) {
  toolHandlers.set(tool.toolSchema.name, tool.handler);
}

// Add transcript tool handlers
for (const [toolName, tool] of Object.entries(transcriptTools)) {
  toolHandlers.set(tool.toolSchema.name, tool.handler);
}

// Add user tool handlers
for (const [toolName, tool] of Object.entries(userTools)) {
  toolHandlers.set(tool.toolSchema.name, tool.handler);
}

export { toolHandlers };


