# Data Protection Impact Assessment — outline

Required under GDPR Article 35 for systematic profiling of individuals' private lives, which this product is. This is the skeleton, with what is already decided filled in; a lawyer completes it.

## 1. Processing description
- **Purpose:** a personal memory aid: surface commitments, changes and deadlines from the user's own mail and calendar.
- **Data:** see the Privacy Policy. Categories: identity, communications content and metadata, calendar, derived facts, usage events, device token.
- **Data subjects:** the user (consenting); their correspondents (non-consenting third parties).
- **Flows:** Google → our servers (encrypted transport) → database (bodies and tokens encrypted at rest) → language-model provider (zero retention) → the user's device.
- **Retention:** per source while connected; deletion cascades and is tested; body retention window: not yet built.

## 2. Necessity and proportionality
- Read-only scopes; the minimum Google scopes that provide the feature.
- Only the last {{BACKFILL_DAYS}} days on first read.
- Drafts, spam and trash are never read.
- Every derived fact keeps provenance; nothing is asserted as true without user confirmation.
- No advertising, no sale, no training.
- **Third parties:** legitimate-interest assessment needed — the correspondent's data is processed only to serve the user, is not used to profile the correspondent, is never used to contact them, and is deleted with the user's data. Mitigations already built: no inference of relationship types or sensitive traits (D5), no content in notifications or logs.

## 3. Risks and mitigations
| Risk | Likelihood | Severity | Mitigation | Status |
|---|---|---|---|---|
| Database breach exposes message content | low | high | bodies and tokens encrypted at rest under a separately held key; evidence quotes remain in the clear (D66) | built |
| Prompt injection via mail plants false facts | medium | medium | untrusted-input handling, quote verification, code-side selection, adversarial test suite | built, tested |
| Impersonation alters trusted facts | medium | medium | founding-address rule, per-link authority, sender authentication | built, tested |
| Model provider retains content | low | high | zero-retention arrangement required before the model path is enabled | policy; unverified |
| Notification leaks content on a lock screen | low | medium | fixed generic text | built, tested |
| Incomplete deletion | low | high | cascade tested table by table; revocation at Google | built, tested |
| Minor uses the service | low | medium | age attestation at sign-up | built |
| Staff read mail | low | high | support tools show identifiers only; Limited Use policy | policy |

## 4. Consultation and sign-off
- DPO / adviser review: pending
- Founder sign-off: pending
