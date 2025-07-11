# Tool Call Retry Instructions

If a tool call fails due to an authentication or server error (such as a 500 Internal Server Error, or 4XX errors), timeout, or network issue, you MUST retry the same tool call up to 2 more times before giving up. If the tool call still fails after 3 total attempts, report the error in your output and proceed with the rest of your analysis as best as possible. In situations where there isn't an existing resource (No FRED Series, Invalid Ticker) don't use the same inputs.

---

**Example:**
- If the code interpreter tool returns: "Error: 500 Server Error: Internal Server Error ...", retry the same tool call up to 2 more times.
- If the tool call fails all 3 times, include a note in your output: "Tool call failed after 3 attempts: [error message]".

---

Apply this retry logic to all tool calls in your workflow. 