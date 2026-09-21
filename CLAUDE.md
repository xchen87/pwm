# CLAUDE.md — Personal World Model

## Mission
Build a production-quality MVP of a Personal World Model: a user-controlled, temporal model of a person's people, relationships, things, commitments, decisions, priorities, events, and supporting evidence.

The product must demonstrate one central experience:
> The system understands what is happening in my life, remembers what matters, and catches important things before I have to remember them.

## Absolute priorities
1. Build the world model before adding broad assistant features.
2. Every important fact must have provenance and confidence.
3. Never silently turn inference into truth.
4. User approval is required for consequential actions.
5. Optimize for useful proactive insight, not chat volume.
6. Keep the architecture modular and provider-agnostic.
7. Protect user data by default.

## MVP scope
IN:
- Gmail read-only ingestion
- Google Calendar read-only ingestion
- explicit user memories
- people/relationship entities
- things/assets
- commitments
- decisions/rationale
- events
- temporal state
- provenance
- World Brief
- Ask Your World
- commitment radar
- decision memory
- source inspection
- draft-only Customer Advocate

OUT:
- autonomous purchases
- money movement
- health data
- social messaging integrations
- WhatsApp/iMessage
- agent marketplace
- broad family suite
- generalized autonomous computer use

## Definition of done
A design partner can connect Gmail + Calendar, wait for ingestion, and then:
- see a trustworthy representation of important people/events/commitments;
- ask natural-language questions and receive source-grounded answers;
- see useful changes and obligations they did not explicitly enter;
- confirm/correct memories;
- inspect the source for important claims;
- understand what the system inferred versus what was confirmed.

## Engineering rules
- Write tests for domain logic.
- Make ingestion idempotent.
- Keep source records immutable.
- Version derived entities where appropriate.
- Preserve provenance.
- Use least-privilege OAuth scopes.
- Add audit logging for agent decisions/actions.
- Do not add dependencies without justification.
- Do not expand MVP scope without an explicit product decision.

## Working style
Before implementing a major feature:
1. State the user problem.
2. State the smallest implementation that proves it.
3. Identify data-model implications.
4. Identify privacy/security implications.
5. Implement.
6. Add tests.
7. Run evaluation.
8. Update documentation.

## Current build order
Follow AGENT.md exactly unless the human founder changes priorities.
