# Threat model: <slug>

Written by `/rails-flow:secure-design` before the acceptance criteria. Checked by `check_threat_model.py`. Revisit when the boundary changes (a new route, token, upload, webhook, role or personal column): edit this file in the same PR.

Status: draft | reviewed   ·   Reviewed: <date>   ·   Unit: <branch or issue>

## What we are building
One short paragraph, and the data flow in a line each: who sends what to which component, what is stored, what is returned.

## Trust boundaries
Each place data or authority crosses from something we do not control into something we do. One bullet per boundary: `<outside> -> <inside>: <what crosses>`.

## Threats
One row per threat. STRIDE: Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege. Decision is one of `mitigate`, `transfer`, `accept`, `eliminate`; an `accept` needs a reason.

| Threat | STRIDE | Component | Decision | Reason |
|---|---|---|---|---|
| <what an attacker or a mistake could do> | S | <where> | mitigate | <control, or why the risk stays> |

## Security requirements
What must be true, one line each, phrased so a criterion can test it (`[security]` criteria citing the `mitigate` rows as `TM-1`, `TM-2`... in table order, #2118). These become acceptance criteria and the questions `security-auditor` asks.
