import * as noteTools from "./contacts/index.js";
import * as recordingTools from "./meetings/index.js";
import * as transcriptTools from "./transcripts/index.js";
import * as userTools from "./users/index.js";

const toolSchemas = [
    // Note tools (renamed from contacts)
    ...Object.values(noteTools).map((tool) => tool.toolSchema),
    
    // Recording tools (renamed from meetings)  
    ...Object.values(recordingTools).map((tool) => tool.toolSchema),
    
    // Transcript/Recording tools
    ...Object.values(transcriptTools).map((tool) => tool.toolSchema),
    
    // User tools
    ...Object.values(userTools).map((tool) => tool.toolSchema),
];

export { toolSchemas };


