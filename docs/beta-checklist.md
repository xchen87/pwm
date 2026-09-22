# Beta release checklist

What must be true before real people connect real accounts. Engineering items link to where they live; the rest are the founder's.

## Google
- [ ] Google Cloud project, OAuth client (Web application) with the production callback URL
- [ ] OAuth consent screen: brand verification, privacy policy URL (`/legal/privacy`), scope justifications, demo video
- [ ] Restricted-scope review submitted; CASA security assessment scheduled (annual)
- [ ] Publishing status "In production" (else 7-day token expiry and a 100-user cap)
- [ ] First real sign-in and sync run and observed (Slice 4 has only ever met a stand-in)

## Legal
- [ ] Privacy Policy and Terms reviewed by a lawyer; placeholders filled (`PWM_LEGAL_*` settings)
- [ ] Sub-processor list confirmed; DPAs signed (hosting, Anthropic incl. zero retention, Expo)
- [ ] DPIA completed (`docs/legal/dpia-outline.md`), legitimate-interest assessment for third-party data
- [ ] Jurisdiction decisions: governing law, EU/UK representative if needed, US state-law thresholds checked
- [ ] Backup retention period set and stated in the policy

## Product
- [x] Age attestation and terms acceptance at sign-up, re-asked when the terms change
- [x] Data export
- [x] Disconnect-and-delete; delete everything, with revocation at Google
- [x] Source inspection for every claim; confirmed vs unconfirmed always visible
- [ ] Body retention window (D57) — not built
- [ ] Gmail deletions propagated (D58) — not built

## Model path
- [ ] API key; live eval on the synthetic mailbox with `--allow-spend`; scores recorded
- [ ] Golden set labelled from the founder's own inbox; scores recorded
- [ ] Zero-retention confirmed for every model that reads message text

## Phone
- [ ] Expo account, EAS project id; Apple and Google developer accounts
- [ ] `app.json` identities, app-link domains, `/.well-known` served over HTTPS
- [ ] Push received on a real device; app links verified; biometric lock tried
- [ ] App Store privacy labels and Play Data Safety form completed
- [ ] Designed notification icon

## Operations
- [ ] Production `PWM_ENVIRONMENT`, `PWM_DATA_KEY` held outside the database, `PWM_PUBLIC_URL` and `PWM_APP_REDIRECTS` set
- [ ] `pwm.cli tick` scheduled; worker running; logs reviewed for content leakage
- [ ] Rate limiting at the edge for `/auth/*`
- [ ] Incident and breach-notification procedure written
