# Scoping: Inference Troubleshooting Assistant

> **Context:** simulated stakeholder engagement. The scoping was done before
> any code was written; see the git history.

## The ask

> "Every time something breaks in our inference stack, someone loses half a
> day digging through vLLM and llama.cpp GitHub issues, and then the papers
> behind them, to figure out whether it's a known problem and what the fix is.
> Can we get something that just answers that?"
>
> (Platform lead, ML inference team)

## Who the users are

Engineers on an ML platform team running open-source inference servers
(vLLM, llama.cpp) in production. They are comfortable with GPUs and serving
configs, but they aren't maintainers of these projects. They usually ask
during an incident or while tuning performance, so time matters.

## What they actually ask

Collected from the team as a starting set:

1. "We're hitting CUDA OOM in vLLM with long-context requests. What settings
   have other people used to fix this?"
2. "What does the 'sequence group preempted' warning mean, and should we
   worry about it?"
3. "Throughput dropped after we upgraded vLLM. Is this a known regression?"
4. "Which llama.cpp quantization format gives the best quality/speed
   trade-off for a 7B model on CPU?"
5. "When does speculative decoding make latency worse instead of better?"
6. "Why is time-to-first-token so high for long prompts?"
7. "How does vLLM's block size setting relate to the PagedAttention design?"
   (needs the paper, not just issues)

## Pain today

- **Searching is slow.** GitHub search is keyword-only and misses rephrasings
  of the same problem. The answer is often buried 15 comments deep under logs
  and "+1"s.
- **Duplicates and stale threads.** The same problem appears in several
  issues, and some answers only apply to old versions.
- **Context is split across places.** Explaining *why* something happens
  often needs the research paper behind the feature, which lives elsewhere.
- **Cost:** the team estimates 30–60 minutes per investigation, several times
  a week.

## Scope

**v1 includes:**
- Closed GitHub issues and discussions from **vLLM** and **llama.cpp**
  (threads with a real back-and-forth, last ~2 years)
- arXiv papers on the techniques those projects implement (PagedAttention,
  quantization, speculative decoding, KV cache)
- Natural-language questions answered with **citations to the exact threads
  and papers**, so engineers can check the source themselves
- A simple web UI and an API

**v1 explicitly excludes:**
- The team's own internal docs, runbooks or tickets (a later phase, using the
  same ingestion pattern)
- Open or unresolved issues, and live sync with GitHub (batch re-ingestion is
  enough for now)
- Taking actions: filing issues, changing configs, auto-remediation
- User accounts and permissions beyond an API key
- Any paid always-on infrastructure (the team has no budget for this yet)

## MVP cut line

The smallest thing that's genuinely useful:

- vLLM threads only (~100–200)
- A command-line script: ask a question, get an answer plus links to the
  threads it came from
- No UI, no papers, no evaluation, no deployment

If this already saves time on the questions above, the rest is hardening.
If it doesn't, we learn that before building anything else.

## What "useful" means

Targets for v1. The baseline gets measured first, and the targets get revised
honestly against it.

| Criterion | Target |
|---|---|
| The right thread or paper is in the top 5 results | ≥ 80% of verified test questions |
| Every answer cites its sources | 100% of answers |
| Citations point to sources that were actually retrieved | ≥ 95% |
| Answers are grounded in the cited sources (faithfulness) | ≥ 0.85 |
| Out-of-scope questions are refused, not answered with a guess | Refused, with no model call |
| Time to an answer | Under ~10 s, vs. 30–60 min today |
| Running cost | $0 / month |

These are checked against a hand-verified question set built *before* the
retrieval pipeline is tuned.

## Risks and assumptions

| Risk | Mitigation |
|---|---|
| Stale answers that fixed an old version | Show the thread date and the versions mentioned with every citation |
| Noisy threads (logs, bots, +1s) drown out retrieval | Thread-aware parsing that separates comments, code and logs |
| Confident wrong answers | Answers must cite sources; citations are validated; out-of-scope questions are refused |
| Free-tier rate limits during a demo | Daily request cap with a clear message; responses cached |
| Licensing of paper text | Show short snippets and link to the original, never the full text |

**Assumptions to confirm with the team:**
- Which vLLM and llama.cpp versions they run, which affects how much stale
  content matters
- Whether open issues would be useful in v2 (they're often where current bugs
  live)
- Whether their internal runbooks should be the next source
