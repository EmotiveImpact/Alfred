# Limited evidence checks, not a truth engine

v0.8 adds the same small evidence checker to source questions and queued conversations.
It runs AFTER reference validation and BEFORE generated claims are returned or persisted.
The existing v0.7 validation still rejects unknown citations and out-of-range lines.

## Implemented rules

Duplicate references within a claim are collapsed. More than four cited lines causes
an explicit broad-citation warning. A numerical token in a claim that is absent from
that claim's cited source passages causes the generated answer to be withheld. An
amount/price/fee/cost question citing no recognisable monetary evidence is also withheld.
These rules use actual canonical source quotes reconstructed by the application, not
model-invented support quotations.

If any rule blocks, the whole generated interpretation is withheld, not just the flagged
sentence. Source passages remain accessible. The distinct status is `model_needs_review`,
not a fake model abstention or network failure. Blocked reply text is not put into the
conversation result store. The model may nevertheless already have received context;
this checker is not an egress or prompt-injection defence.

## Limits that must remain visible

These are literal English-language heuristics, not semantic entailment. They do not
establish which source is true, resolve conflicting reports, reliably understand
negation, match all currencies, or verify that a passage answers a question. A number
can be present in a cited passage but attached to the wrong entity. A true but irrelevant
sentence can still pass. Valid paraphrases, inferred sums and word-form numbers may be
incorrectly blocked or missed. No confidence score or automatic truth stamp is produced.

The checker is therefore an extra rejection layer, not production-model validation.
Manual review of actual outputs and a broader independently scored question set remain
necessary. Reviewed memory is also human judgement, not a substitute semantic verifier.

## This increment's experiments

The earlier v0.7 small-Qwen inference trials and their missing-price/conflict failures
remain historical evidence. A new live-model comparison workflow was blocked by a tool
safety check before it was committed or run. That operation was not retried through a
different route. No new stronger-model benchmark or actual inference is claimed here.

Tests use explicit synthetic model doubles. They verify the rules in both the synchronous
question path and the actual persistent conversation worker, including that an unsupported
number is not returned/stored. Browser acceptance tests do not establish model quality.
The optional configured loopback model remains off by default and has no execution tools.
