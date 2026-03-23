Compare two code review policies for the same pull request.

The reviewer model and reviewer system prompt are held constant.
Only the AGENTS.md guidance differs between the baseline and candidate reviews.

Pick the better review overall based on correctness, usefulness, and noise.
Prefer the review that finds more important real issues without adding weak or
speculative comments. Return `tie` only when the two reviews are effectively
equivalent in quality.
