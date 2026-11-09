# rubric-escrow

Bounty escrow for GenLayer where the payout is decided against a public rubric,
and every "yes" has to be backed by a quote that validators can check.

The usual way to build "AI-judged" bounties is to send a deliverable to a model,
ask for a score, and let validators ask the same question again with a
comparative equivalence principle. That leaves two problems: the judgement is
a black box, and nothing stops a leader (or a prompt injection inside the
deliverable) from asserting things that are not there.

`RubricEscrow` splits grading into a small non-deterministic part and a
deterministic part that anyone can audit:

- the poster writes criteria with weights, marks some as **required**, and sets
  a pass score;
- the model only answers "met / not met" per criterion and must attach a
  **verbatim quote** from the deliverable for every "met";
- the contract keeps a "met" only if the quote is actually present in the page
  text (plain normalized substring match, no model involved);
- score and payout are computed from the weights in ordinary Python.

Deployed on GenLayer Studio (studionet):
[`0x819cDfe78cD376537342c03D00D38988Be297ffF`](https://explorer-studio.genlayer.com/address/0x819cDfe78cD376537342c03D00D38988Be297ffF)

## Flow

```
poster                      contract                                   submitter
  │ create_bounty(+reward) ─▶ store brief, rubric, reward
  │                                                     ◀── submit(id, url)
  │                         run_nondet:
  │                           leader:    render url ─▶ grade ─▶ ground quotes
  │                           validator: render url ─▶ grade ─▶ ground quotes
  │                                      + check leader's quotes against its own copy
  │                                      + compare decision / required / score band
  │                         deterministic:
  │                           score = Σ weight(met) / Σ weight
  │                           pass  = all required met and score ≥ pass_score
  │                           pass  ─▶ status=awarded, credit submitter
  │                                                     ◀── withdraw()
```

## Consensus design

The block runs through `gl.vm.run_nondet_unsafe` with a custom validator. The
validator fetches and grades the page independently and then accepts the
leader's verdict only if all of the following hold:

1. **Leader evidence exists in the validator's copy of the page.** Every quote
   behind a leader "met" is normalized (case, whitespace, curly quotes, dashes)
   and must be a substring of the page *as the validator fetched it*, 8–240
   characters long. A leader cannot invent evidence, and a deliverable that
   changes between fetches cannot keep its old quotes.
2. **Same payout decision.** `decide()` applied to the leader's verdict and to
   the validator's own verdict must agree.
3. **Same verdict on every required criterion.** Two runs that both pass but
   for different hard reasons are not considered equivalent.
4. **Soft criteria within a band.** The weighted scores may differ by at most
   `SCORE_BAND` (20) points, so honest disagreement on a nice-to-have does not
   block consensus.
5. **Same claim result and well-formed output** (one entry per criterion).
6. **Errors are judged, not waved through.** If the leader reports the page as
   empty or unreachable, a validator that can read it votes against.

Steps 1, 2 and 3 are deterministic checks over the model's structured output,
which is what makes the verdict reproducible across nodes even though the
model's wording is not.

### Claim tag

With `require_claim = true`, the deliverable has to contain the submitter's
address (case-insensitive). The check runs before the model is called, so a
copied deliverable costs one fetch and is recorded as failed with
`claim tag missing from deliverable`. It is a cheap and verifiable way to bind
a public page or gist to the account that is asking to be paid.

### Prompt injection

The deliverable is untrusted input that goes straight into a prompt. The prompt
tells the model to ignore instructions inside it, but the real protection is
structural: an injected "mark everything as met" still needs a real quote for
each criterion that the page genuinely contains, and the score is computed by
the contract rather than taken from the model. See
`test_prompt_injection_cannot_create_evidence`.

## State

```python
bounties:    TreeMap[str, Bounty]                 # poster, brief, reward, pass score, status, winner
criteria:    TreeMap[str, DynArray[Criterion]]    # text, weight, required
submissions: TreeMap[str, Submission]             # "<bounty>:<n>" -> verdict, score, mask, quotes
attempts:    TreeMap[str, u32]                    # "<bounty>:<address>" -> attempts used
credits:     TreeMap[Address, u256]               # pull-payment balances
next_id:     u64
```

Payouts go through `credits` and `withdraw()` (pull payments), so awarding a
bounty never transfers value in the middle of a consensus-heavy transaction.

## Interface

| method | kind | notes |
|---|---|---|
| `create_bounty(title, brief, criteria, pass_score, max_attempts, require_claim, deadline_ts)` | payable write | `msg.value` is the reward; `deadline_ts = 0` means no deadline; returns the bounty id |
| `submit(bounty_id, url)` | write | grades the deliverable; pays out on pass |
| `cancel(bounty_id)` | write | poster only; allowed before any submission, or after the deadline with no winner |
| `withdraw()` | write | sends the caller's credited balance |
| `get_bounty(id)` / `get_submission(id, n)` | view | |
| `attempts_left(id, address)` / `credit_of(address)` / `bounty_count()` | view | |

`criteria` is a list of objects:

```json
[
  {"text": "Explains how to run the indexer locally", "weight": 30, "required": true},
  {"text": "Documents every environment variable",   "weight": 30, "required": true},
  {"text": "Includes a troubleshooting section",     "weight": 20},
  {"text": "Mentions the supported Postgres versions", "weight": 20}
]
```

Rules enforced on submit: the bounty is open and before its deadline, the
submitter is not the poster, the URL is https, and the submitter still has
attempts left (`max_attempts` per address, 1–10).

## Example on studionet

```bash
genlayer network set studionet
genlayer deploy --contract contracts/rubric_escrow.py

genlayer write <address> create_bounty --args \
  "Explain the Equivalence Principle" \
  "A page that teaches a new builder how GenLayer validators agree on non-deterministic results." \
  '[{"text":"Explains why validators need a way to agree on non-deterministic outputs such as web data or LLM answers","weight":40,"required":true},
    {"text":"Describes at least one built-in equivalence principle function and when to use it","weight":40,"required":true},
    {"text":"Includes a code example","weight":20,"required":false}]' \
  60 3 false 0

# from a different account
genlayer write <address> submit --args 1 https://docs.genlayer.com/developers/intelligent-contracts/equivalence-principle
genlayer call  <address> get_submission --args 1 0
```

On the deployment above this submission was accepted by three agreeing
validators with score 100, and the stored evidence includes quotes such as
`"result = gl.eq_principle.prompt_comparative("` for the code-example
criterion.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

genvm-lint check contracts/rubric_escrow.py
pytest -q
```

Tests run in gltest direct mode with mocked pages and model output:

- `tests/test_rules.py` – normalization, grounding, score rounding, required
  criteria, defensive parsing of model output, claim handling.
- `tests/test_escrow.py` – bounty lifecycle: payout, failing a required
  criterion, fabricated quotes, prompt injection, copied work, attempt limits,
  deadlines and cancellation rules.
- `tests/test_validator.py` – the validator on its own: honest leader, soft
  disagreement inside the band, a flipped payout decision, invented quotes, a
  page that changed between fetches, claim mismatch, malformed output and
  false versus real "unreachable" errors.

## Limitations

- Grading is only as good as the criteria. Criteria should describe things that
  can be pointed at in the text ("documents every environment variable"), not
  taste ("well written").
- The page is read with `render(mode="text")`; content that only appears after
  interaction or behind a login cannot be graded.
- The first passing submission wins. For competitions where the best of many
  entries should win, collect submissions first and grade them in one round.

## License

MIT
