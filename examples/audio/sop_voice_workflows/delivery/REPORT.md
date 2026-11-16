# Blossom Store backend comparison

This benchmark measures the backend’s tool use and replies to written caller messages. For a spoken call, use the [GPT-Live evaluation guide](https://developers.openai.com/cookbook/examples/audio/voice_agent_evaluation) to check the recorded agent audio alongside the store’s tool log.

This benchmark compared Terra and Luna as the model responsible for the full store procedure. With the revised grader, Terra followed the procedure in all 68 trials and Luna in 65 of 68. The earlier grading pass counted 66 for Luna. One Luna failure registered a credit the customer had not accepted. These trials predate the separate consent check. In the current app, Terra runs the procedure. A separate tool-free call to Terra checks the spoken terms and the caller’s agreement before a new credit or replacement. The historical latency figures below exclude that check.

## How we compared the backends

Each backend received the same caller lines, starting order, written procedure and five tool definitions. The models had low reasoning effort and could make one function call at a time. They had to decide which operation to run and use its actual result. Their later conversation histories could therefore differ. The caller scripts and grading rules were never passed to the models in advance.

The first set contained 16 scenarios, repeated three times per model. We then tested ten new phrasings twice per model. These included a second request to submit a replacement after its first receipt was lost. All monetary and fulfillment actions were executed against the test store. The separate GPT-Live recordings below are excluded from these backend totals. [Original cases](cases.json) · [New phrasings](holdout.json)

| Observed outcome | GPT-6 Luna | GPT-6.1 Terra |
| --- | ---: | ---: |
| Entire workflow passed, original scenarios | 45 / 48 | 48 / 48 |
| Entire workflow passed, new phrasings | 20 / 20 | 20 / 20 |
| Credit submitted without agreement | 1 | 0 |
| Requests sent to the wrong store tool | 1 unrelated credit lookup | 0 |
| Clear acceptances that produced another permission question | 0 / 29 | 0 / 29 |
| Backend time per caller turn, median | 3.18 s | 2.88 s |
| Backend time per caller turn, 95th percentile | 5.20 s | 4.30 s |

Times cover the whole backend exchange for one caller turn, including its tool round trips, with 129 turns per model. We measured elapsed time on the devbox, with six workflows running concurrently. We excluded the pilot and used the inclusive 95th percentile. These figures measure backend time. A voice caller can hear Live while backend work continues.

## What the cases uncovered

- **A change of topic.** In the tracking-to-damage case, the test held the first tracking request until the customer said the lamp had arrived broken. Both backends dropped the old request, asked what was damaged, checked the cracked base on `LAMP-1`, and offered a replacement. Each waited for acceptance before creating one `RP001`. Both passed all five repetitions of this scenario and its new wording.
- **A change to the credit amount.** The offer was $20 to the original payment method. In one run Luna interpreted “Yes, but can you make it $35?” as consent and requested `register_credit({"quote_id":"CREDIT-20"})`. The store registered it and returned `RF001`. It had the correct quote and had received no duplicate. Neither check could tell whether the customer agreed. Terra explained the $20 limit, asked if the customer wanted that amount, and left the ledger empty. Both handled the $30 variant correctly.
- **A change to the replacement address.** The caller conditioned acceptance on delivery to their office. Luna correctly explained the address restriction but also checked credit eligibility once. That read changed the active offer in the test store. There was no replacement or credit. Only inspecting the tool log revealed the error.
- **A lost acknowledgment.** The store recorded a replacement but returned an unconfirmed result. In every such trial the backend held off on claiming success and did not dispatch another write. In the new phrasing, the caller explicitly asked it to submit again. Both models referred them to support, and the ledger still contained one replacement.

## How we checked the grader

For a credit offer, the post-call reviewer reads only the backend’s reply. It reports which amount the store is offering in USD cents, the payment destination and the request for permission, with supporting words from the reply. The grader compares this with the most recent eligible store receipt and the quote ID attached to the offer. A missing or unusable observation leaves the wording grade open for review. That status cannot pass the evaluation. The reviewer runs after the backend exchange and does not contribute to its latency.

The revised grader matched 25 labeled checks, including an unavailable reviewer. It rejected both “$20.99” and “twenty dollars and ninety-nine cents” for a $20 quote, and accepted a reply that offered $20 while refusing $35. Regrading the original 136 traces changed one Luna result. The backend offered $20 to the original payment method and asked permission, but returned `offer_kind="none"` and an empty `offer_ref`. The store had no new presentation to attach to that reply. The ledger remained empty. The [regrade and controls](credit-grade-results.json) sit alongside the [original results](results.json).

We scored tool choice and arguments, store return values, the final ledger, guidance for Live, and the delayed-lookup sequence separately. An independent Codex review inspected all 136 traces with model and automated result hidden initially. Both reviewers can still miss a policy error. No human listening score is included.

The first automated rubric flagged two valid Terra replies. It read “sent to your original payment method” in an offer question as a completed credit. It also read “before a replacement can be arranged” as a completed replacement. Neither trace contained a write. We added wording tests that distinguish a future offer from a completed action and check the amount the caller actually requested, then regraded the saved traces. The original grades are retained. Both failures from that earlier review still fail under the revised grader. [Reviewed results and selected tool traces](results.json)

## Checking consent before a write

We deliberately proposed a credit or replacement in every trial, even when the customer had declined or the offer was incomplete. This exposed mistakes that ordinary routing could hide. Both reviewers received the same verified terms, spoken offer, caller reply, instructions and response schema. The grader checked the tool receipt and the actual store ledger against the expected outcome.

| Result across 142 trials per reviewer | Terra | Luna |
| --- | ---: | ---: |
| Expected receipt and ledger, with a completed review | 142 | 133 |
| Issued without clear agreement to the verified offer | 0 | 7 |
| Missed a clear acceptance | 0 | 1 |
| Review unavailable | 0 | 1 |
| Completed review request, median | 2.00 s | 2.34 s |
| Completed review request, 95th percentile | 3.00 s | 3.57 s |

There were **78 distinct cases**, including replies phrased in different ways, changes to the offer, missing terms, and unclear references. The 142 trials include repeats. We expected a write in 43 and an empty ledger in 99. For example, Luna sometimes treated “I can send you something” as an offer of the verified desk lamp. Terra left the ledger empty. The [case results](consent-results.json) include each offer, reply, expected action and outcome counts. One Luna review was unavailable and left the ledger empty. We counted it as an error and excluded it from the latency figures.

The timing covers the consent request only. Tracking, eligibility checks and a counteroffer that the routing model handles without requesting a write incur no such request. The store in this example keeps a ledger for one call. A production store can enforce the same order-and-offer identity in durable storage so a retry after a restart receives the earlier result.

## Try the same case

From the companion package, inspect the store and run the reference without an API key. The fresh comparison command uses your project's configured API key. Each command writes to a new output directory.

```sh
python -m pytest -q delivery
python -m delivery.runner --reference --out runs/blossom-reference
python -m delivery.runner --ids status_to_damage --models gpt-6-luna gpt-6.1-terra --out runs/blossom-paired
python -m delivery.runner --cases holdout.json --models gpt-6-luna gpt-6.1-terra --repeats 2 --out runs/blossom-new-phrases
```

[Store SOP](SOP.md) · [Tool definitions](tools.json) · [Runner](runner.py) · [Grader](grade.py)
