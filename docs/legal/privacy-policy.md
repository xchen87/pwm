# Privacy Policy

**Draft for legal review. Not yet in force.** Placeholders in curly braces are filled from server configuration.

Last updated: {{TERMS_VERSION}}

{{COMPANY}} ("we") provides {{PRODUCT}}, an application that reads the email and calendar accounts you choose to connect and builds a private, personal record of the people, commitments, events and decisions in your life, so it can remind you of what matters and tell you what changed. This policy explains what we collect, why, and what control you have.

## What we collect

**Account.** When you sign in with Google we receive your Google account identifier, your email address and your name. We use them to create and identify your account. We never see your Google password.

**Connected data.** With your permission, we read, read-only:
- **Gmail**: message headers (sender, recipients, subject, date, labels, authentication results) and the text of messages from the last {{BACKFILL_DAYS}} days, then new messages as they arrive.
- **Google Calendar**: your primary calendar's events (title, time, location, description, attendees).

We do not read drafts, spam or trash. We cannot send, delete or change anything in your accounts.

**What we derive.** From connected data and from notes you type, we extract candidate facts: a commitment, a date, a price, a contact detail, a decision. Every derived fact keeps the exact words it came from, where they came from, and whether you confirmed it. Nothing derived is treated as true until you confirm it.

**Usage.** We record which features you use (for example that a brief was opened or an item dismissed), by name and identifier only, never with content.

**Devices.** If you enable notifications, we store a push token that addresses your phone.

## How we use it

Only to provide the features you see in the application: showing what changed, what needs attention, answering your questions, and notifying you that a brief is ready. Specifically, we do **not**:
- use your data for advertising, or sell it;
- use your data to train machine-learning models;
- let a person read your messages, except with your explicit permission for specific messages when you ask for support, or where the law requires it.

Our use of information received from Google APIs adheres to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the Limited Use requirements.

## Who else processes it

We use service providers to run the application. Each may act only on our instructions under a data-processing agreement. The current list, with what each receives, is published at {{PUBLIC_URL}}/legal/subprocessors and is part of this policy. In particular, the text of your messages is sent to a language-model provider to be read and summarised; we require an arrangement under which the provider does not retain that text or use it for training, and we do not enable that provider until it is in place.

We do not share your data with anyone else, except to comply with a legal obligation, to protect against abuse or fraud, or with your consent.

## Other people's data

Your mail and calendar contain other people's names, addresses and words. We process that information only to serve you, keep the minimum needed, never contact those people, and never build anything about them beyond what appears in your own records. If you are in the EU or UK, our basis for processing your own data is the contract with you (these features are the service), and our basis for other people's data in your mail is our legitimate interest in providing the service you asked for, which we assess and document before the beta.

## How long we keep it

- Connected data and everything derived from it: for as long as the source is connected. Disconnecting a source deletes what it brought in; our access at Google is withdrawn when your last Google source is disconnected, or when you delete your account.
- Your account and notes: until you delete your account.
- Message text: {{RETENTION_NOTE}}
- Backups: up to {{BACKUP_DAYS}} days after deletion.

## Security

Connected data is transferred over encrypted connections. Your Google access token and the text of your messages are encrypted at rest under a key that is not stored with the data. The short excerpts that support each derived fact, and the facts themselves, are stored in ordinary form so they can be shown and searched. Access to production systems is restricted to the people who run the service, and our support tools are built to show identifiers and metadata, not message content.

## Your rights and controls

Inside the application you can, at any time:
- see the source of every claim, and confirm, correct or dismiss it;
- disconnect any source, which deletes what it brought in and withdraws our access at Google;
- export the data we hold about you as a file;
- delete your account and everything in it.

Depending on where you live you may also have legal rights to access, correct, delete, restrict or port your data, or to object to its processing. Write to {{CONTACT_EMAIL}}. If you are in the EU or UK you may also complain to your data-protection authority.

## Age

The application is for adults. You must be at least {{MINIMUM_AGE}} to create an account, and we ask you to confirm that when you sign up. We do not knowingly collect data from anyone younger; if we learn that we have, we delete it.

## International transfers

Our servers are located in {{HOSTING_REGION}}. If you use the application from elsewhere, your data is transferred there. Where the law requires, transfers are covered by standard contractual clauses or an equivalent mechanism.

## Cookies and local storage

The web version keeps your sign-in for the current browser tab only and uses no cookies or tracking. The phone app keeps your sign-in in the phone's secure storage.

## Automated decisions

The application makes no decision with legal or similarly significant effect on you. It suggests; you confirm.

## If something goes wrong

If we learn of a breach that puts your data at risk we will tell you and, where required, the authorities, without undue delay.

## Changes

When this policy or the terms change materially, the application asks you to accept the new version before you continue.

## Contact

{{COMPANY}}
{{ADDRESS}}
{{CONTACT_EMAIL}}
