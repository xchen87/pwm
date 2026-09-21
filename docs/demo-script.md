# Demo script

A ten-minute walkthrough of the MVP on a laptop, with no API key and no real mailbox.

## What the audience should take away
1. It found things in mail and calendar that the user never typed in.
2. It never states a guess as a fact — everything unconfirmed says "possible", and one tap shows the exact words it came from.
3. It noticed what *changed*, and when two sources disagree it says so instead of picking one.
4. It will not be talked into things by a hostile email.

## Be straight about what this is
- The mailbox is **synthetic**: one invented person (Alex Rivera), 122 messages, calendar entries and notes, including 68 pieces of noise and 10 attack emails.
- Understanding the mail is done by a **rule-based stand-in**, not a language model. It is good enough to show the product and deliberately limited: it misses things a model would catch (see "Known gaps" below). The model-backed extractor is written and unit-tested but has never been run against the live API.
- The clock is pinned to **Saturday 12 September 2026**, inside the mailbox's timeline.
- There is no login: the API serves one local user and must stay on localhost.

## Start
```sh
scripts/demo.sh            # starts empty, at "Connect your life"
scripts/demo.sh --loaded   # mailbox already connected, first brief ready
scripts/demo.sh --keep     # exactly as you left it last time
```
Open http://localhost:8081 and switch the browser to a phone-sized view (dev tools → device toolbar). The same code runs in an Android emulator or Expo Go (not yet tested there).

## Walkthrough

**0. Connect your life.** The four promises on the screen are the product's rules, not marketing: read-only, every claim shows its words, a guess stays a guess, disconnect deletes. Gmail and Calendar are shown but unavailable (they need Google's verification). Tap **Connect the demo mailbox**: 122 items are read, most are discarded as noise before any understanding is attempted, and the first brief is ready.

**1. Your World (home).** "Here's what it understood without being told anything."
- *Sources disagree*: the calendar says Mom's dinner is Sunday at 6; an earlier email said Saturday. It shows both rather than picking. (Priya's "change of plan" email would settle it, but it came from a second address the user has not confirmed is hers — so it is not allowed to overrule anything. This is the impersonation defence at work.)
- *Changed*: the kitchen quote went from $18,400 to $19,950; the dentist moved the appointment. Each card shows the new words **and** the earlier words they replaced.
- Point at "It looks like…": nothing here has been confirmed yet, so nothing is stated as fact.

**2. Open the kitchen-quote card → "Where this came from".**
- The sentence is highlighted inside the message, with sender, subject and date.
- "How I know": stated in the message / confidence / not confirmed / found by.
- "Related": the earlier quote it replaced.

**3. Needs attention → See all.**
- Promises Alex made ("I'll send you the Q3 numbers by Friday" — now overdue) and promises made *to* Alex (Tom's review, Jordan's contract, the plumber).
- Deadlines from third parties: the tax payment, the lease reply.
- **Confirm** the Q3 numbers → it moves to "On your list" and the label loses "Possible".
- **Edit** Tom's review date → your version replaces it and is confirmed; the original stays on record.
- **Dismiss** Helen's "I'll be out next Friday" — a false positive, left in on purpose. Dismissed items do not come back when mail is reprocessed.

**4. World Brief.** Tap *World Brief*, then *Make a fresh brief*.
- A short, ranked digest: what is due, what changed, a few things to review, price changes (StreamMax, car insurance, the dishwasher's return window).
- At most four unreviewed guesses per brief, never a low-confidence one.
- "Was this useful?" feeds the measurement the beta will run on.
- The notification that announces a brief says only "Your World Brief is ready". No names, amounts or quotes ever go to a lock screen.

**5. Ask your world.**
- "What did I promise Tom?" → the Q3 numbers, with the quote and a link to the source.
- "What is the kitchen quote now?" then "What was the kitchen quote originally?" → it keeps history.
- "What did I promise Beatrice?" → "I haven't seen anything about 'beatrice'." It declines rather than guesses.
- "Did I agree to pay PayFast $500?" → nothing. That claim exists only in an attack email.

**6. Remember this.** Home → *+ Remember something* → "The spare key is with Marguerite next door."
- It appears under Remembered, in your exact words. Ask "Where is the spare key?".
- Try "Renew the car registration by October 20." — the note is kept verbatim, and the deadline it *read out of it* arrives as a possibility to confirm. Open the note → **Forget this** removes it and everything derived from it.

**7. The hostile mail (optional, for a technical audience).**
The mailbox contains ten attacks: "ignore previous instructions", a fake system message, hidden HTML, a forged quoted reply putting words in Alex's mouth, a look-alike of Alex's own address, JSON smuggling, and requests to delete or exfiltrate. None of them produced an item. Run `uv run python -m pwm_eval.run --system heuristic --no-record` and show `injection_clean True`.

**8. Your data.** Home → *Connections and your data*. **Disconnect and delete its data** removes all 122 items and everything understood from them — the home screen empties — while the note you typed stays. **Delete everything** returns to "Connect your life".

## Known gaps you may be asked about
- The stand-in misses the decision "Let's keep the CR-V until 2028…" (no "we decided"), Priya's "change of plan" message, and the contradiction between the coach's and the league's registration deadlines. A model-backed extractor is expected to catch these; that is unproven until it is run.
- Subjects are crude ("Your appointment has been rescheduled" rather than "Dentist appointment") because the stand-in uses the email subject.
- No real Gmail/Calendar connection, no accounts, no phone build, no real push yet — see `docs/PROGRESS.md` for what each needs.
- Scores from this mailbox are not product quality: the same author wrote the rules and the mail.
