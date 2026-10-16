<!--
HOW TO USE THIS FILE
1. Everything in [SQUARE BRACKETS] is something only YOU can fill in: real numbers, real quotes, links.
2. Delete any section you cannot fill honestly (My First User, Entire, etc.). Do not invent anything.
3. Paste the result into a new DEV post using the Hacktoberfest Week 2 template. Keep the tags #devchallenge and #hf26challenge.
4. Read it aloud once. Change any sentence that does not sound like you.
-->

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 2: Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12)*

## What I Built

**Tallyroll** is a bill sorter for small restaurants. You drop in photos of supplier bills and receipts (vegetable market, butcher, dairy, gas, electricity). It reads each one, sorts it into a kitchen category, flags the ones it is unsure about, and gives you one spreadsheet to hand to your accountant.

Who would pay: a restaurant owner who spends [X] hours at the end of every month sorting a shoebox of paper bills. I spoke to one: [name or "a restaurant owner in CITY", only with their permission]. [One real sentence about how they do it today.]

The part that makes it worth paying for is trust. A restaurant's bills show who they buy from, what they pay and how much they make. Tallyroll never sends any of it anywhere.

## Demo

[Link to your video or screen recording, 60 to 90 seconds. Turn Wi-Fi off on camera. That is the whole pitch.]

## Code

[Paste your GitHub link here, on its own line, to embed the repo.]

## How I Built It

I am new to programming. I built Tallyroll by directing an AI coding assistant (Claude) and checking its work against real bills. [Keep this line: honesty about this will help you, not hurt you.]

- **Model:** Gemma, Google's open-weight model, running locally through Ollama. I used `gemma3:4b` [and/or `gemma4:e4b`, say which one you actually used and why]. Both can look at pictures, so there is no separate text-reading step.
- **Structured output:** I give Gemma a JSON schema, so it answers in a fixed shape (vendor, date, total, tax, category, line items, how sure it is). The category must come from a list of 15 restaurant categories.
- **Don't trust the model blindly:** a clean-up layer fixes number and date formats (`Rs. 9,759.75`, `09-Oct-26`, day-first vs month-first) and flags a bill for a human check when the date or total is missing, the line items don't add up, the photo is hard to read, or it looks like a duplicate.
- **Human in the loop:** every bill opens next to its photo so a wrong number takes seconds to fix.
- **No dependencies:** the whole server is the Python standard library. The owner installs two things (Python and Ollama), double-clicks two files, and it works.
- **Design:** the receipt printer on the home page prints each bill as it is read, because watching it work is how an owner learns to trust it.
- **Tests:** the clean-up layer has unit tests that run in GitHub Actions on every push. [Keep only if you uploaded the .github folder and the green tick shows.]

How well did it work on real bills? [Fill in from your test with the owner's bills: "I tried N bills. It got M fully right, F were flagged for a check, W had a wrong number that was not flagged. A typical bill took S seconds on my [laptop model, with or without graphics card]." Report the wrong ones honestly. It makes everything else more believable.]

## Why Does Open Innovation Matter?

- **Privacy is the product.** A closed cloud API would mean uploading every supplier bill, which shows who the restaurant buys from, what they pay and their margins. With an open-weight model the bills never leave the computer.
- **It costs nothing per bill.** A restaurant can have hundreds of bills a month. Per-image API pricing would eat the saving. Running Gemma locally costs only electricity, so I can sell it as a one-time setup rather than a subscription. [Only keep if true: your pricing idea.]
- **It works offline.** Kitchens and back offices do not always have good internet. [Mention the Wi-Fi-off demo.]
- **I can swap the model.** The model name is one setting. When a better Gemma comes out, the owner changes one line. With a closed API the vendor changes the model under you and you find out when your numbers shift. [If you tested both Gemma versions, add what you saw.]

What open did **not** fix: small models still misread digits on blurry bills. That is why the photo sits next to the numbers and doubtful bills are flagged.

## My First User

[Only fill this in if it really happened. Delete the section otherwise.]

I sat with [name/role] and ran [N] of their real bills from [month].

- What they said: "[their exact words]"
- What went wrong: [one honest thing]
- What they asked for next: [their request]
- Would they pay? [Yes / no / "not sure", and what number they named, if any.]

## Prize Categories

- **Best Use of Gemma**: the whole project runs on it.
- **Best Use of GitHub Copilot**: [only if true] automated tests on every push with GitHub Actions.
- **Best Use of a .tech Domain**: [only if you put a page live on a .tech domain and link it here. Otherwise delete this line.]

<!-- Thanks for participating! -->
