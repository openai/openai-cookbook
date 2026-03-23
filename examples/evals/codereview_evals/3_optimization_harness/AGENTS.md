Optimize the candidate code review policy without sacrificing overall review quality.

Use pairwise comparison to decide whether the candidate is better than the
current champion, but treat pairwise win rate as only one component of the
objective. The candidate must also maintain a strong pointwise benchmark score.

When revising the candidate:
- prefer grounded, high-signal review behavior
- do not add broad style guidance that increases noise
- do not trade away correctness for aggressiveness
- improve both `AGENTS.md` and the reviewer system prompt when the results justify it
