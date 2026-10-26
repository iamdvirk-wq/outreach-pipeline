# Build Brief: Local Business Outreach Pipeline

## How to use this file (for you, not for Claude Code)

1. Make a new empty folder on your computer, e.g. `outreach-pipeline`.
2. Save this file into it as `BUILD_BRIEF.md`.
3. Open Claude Code in that folder and say:
   > Read BUILD_BRIEF.md. Ask me any setup questions you need answered, then build Phase 1 only. Stop when Phase 1 works and tell me how to test it.
4. Test each phase yourself before saying "build the next phase". Don't ask for everything at once; a working small system beats a broken big one.

Before Phase 2 you'll need an Anthropic API key. Before Phase 4 you'll need an email account you send from, and ideally a separate outreach domain. Before Phase 5 you'll need a Google Maps Platform API key with the Places API enabled.

---

## Brief for Claude Code

### 1. What we are building

A local web app for a solo web-design business in Australia. It finds local businesses that would benefit from a new or improved website, researches each one, drafts a personalised outreach email for me to review, sends it from my mailbox **only after I approve it**, and tracks replies.

The app has two main parts:

- **A tracking dashboard (website):** shows every business, its research, the email sent, when it was sent, whether they replied, and the outcome.
- **A lead finder:** runs on a schedule, finds new businesses across many industries and locations, removes duplicates, and adds them to the queue for research.

The user is not a professional developer. Prefer simple, well-documented choices over clever ones. Explain setup steps in plain language in the README.

### 2. Non-negotiable rules (legal compliance and safety)

These rules exist because I operate in Australia under the Spam Act 2003. Build them into the code, not just the documentation.

1. **No address harvesting.** The app must never crawl, scrape or extract email addresses from websites, directories or Google Maps, and must not import email addresses from any scraper output. The Spam Act prohibits using address-harvesting software or lists produced by it. The research step may record the URL of the business's contact page and whether an email address appears to be published there. The email address field is filled in **manually by me** in the dashboard, with a checkbox confirming "I found this address published on the business's own website or listing."
2. **Human approval for every email.** Nothing is sent without me clicking Approve & Send on that specific email. No bulk send button, no auto-send, no auto-follow-up.
3. **Daily send cap.** Default 20 per day, configurable, hard maximum 50. Space sends at least 3 minutes apart.
4. **Every email identifies me and has an opt-out.** Every outgoing email includes my name, business name, ABN, phone and website. It ends with an opt-out line such as "If you'd rather not hear from me, just reply 'no thanks' and I won't contact you again." Opt-out replies must be honoured automatically, well within the Act's 5-business-day limit.
5. **Do-not-contact list.** Any business that opts out, asks not to be contacted, or that I mark manually goes on a permanent suppression list, checked by domain and email before every send. This list survives database resets and is backed up.
6. **No repeat pestering.** Maximum one follow-up per business, at least 5 business days after the first email and only if I approve it. Never contact the same domain again within 180 days after that.
7. **Skip businesses that say no.** If the research step finds wording like "no solicitations" or "no marketing emails" on the site, mark the lead Disqualified.
8. **Evidence-backed claims only.** Every issue mentioned in a draft email must come from a recorded audit finding with evidence. The drafter must never invent problems, statistics, results or compliments.
9. **Lead sources must follow their terms.** Use the official Google Places API, not scraping of Google Maps. Read the current Google Maps Platform terms on storing Places data and follow them; for example, store `place_id` long-term and refresh other details as the terms require. Also support importing CSV files I collect myself.
10. **Polite website fetching.** When auditing a business's site, respect robots.txt, use a clear user agent, wait at least 2 seconds between requests to the same domain, and fetch only the homepage plus up to 3 key pages (contact, services, about).
11. **Secrets stay secret.** API keys and passwords live in a `.env` file that is git-ignored. Never print them in logs.

### 3. Tech stack

- **Python 3.11+**
- **FastAPI** with server-rendered **Jinja2** templates and **HTMX** for interactivity, with no separate frontend build step
- **SQLite** via **SQLAlchemy**, one database file
- **APScheduler** for scheduled jobs (lead finding, reply checking) while the app runs
- **httpx** plus **BeautifulSoup** for fetching and parsing websites
- **Anthropic Python SDK** for research summaries, reply classification and email drafts. Default model `claude-sonnet-5-5`; check the Anthropic docs for the current model name and make it configurable in `.env`.
- **Google PageSpeed Insights API** for mobile performance scores
- **SMTP** for sending and **IMAP** for reading replies, so it works with Gmail (app password), Outlook or a custom domain mailbox
- Simple, clean CSS: readable, mobile-friendly, light and dark mode
- Runs locally at `http://localhost:8000`. Single command to start. Works on macOS and Windows; ask me which I use.

### 4. Data model

**Business**
- id, name, industry/category, suburb, city, state, address, phone, website URL, domain (normalised, unique), google_place_id (nullable), rating, review_count, source (places_api / csv_import / manual), date_found
- contact_page_url, email_published_flag (detected yes/no/unknown)
- contact_email (entered manually), email_confirmed_published (bool, set by me), contact_name (optional)
- status: `new → researching → researched → qualified / disqualified → draft_ready → approved → sent → follow_up_sent → replied → won / lost / opted_out`
- disqualify_reason, qualification_score, notes, tags

**AuditFinding**
- business_id, check_name, passed (bool), severity (low/medium/high), evidence (what was observed, e.g. "no viewport meta tag in homepage HTML"), checked_at

**ResearchSummary**
- business_id, what_they_sell, likely_customers, what_matters_in_this_industry, positive_detail (from their own site or public review themes, paraphrased), suggested_angle, created_at

**Email**
- business_id, type (initial / follow_up), subject, body, status (draft / approved / sent / failed), message_id, sent_at, approved_at, edited_by_me (bool)

**Reply**
- business_id, email_id, from_address, received_at, snippet, classification (interested / question / not_interested / opt_out / auto_reply / bounce / unclear), handled (bool)

**DoNotContact**
- domain, email, reason, added_at

**Settings**
- daily_send_cap, sender details (name, business name, ABN, phone, website, signature), target industries list, target locations list, leads_per_run, qualification thresholds

### 5. Build phases

Build and test one phase at a time. After each phase, stop, summarise what works, and tell me exactly how to test it.

#### Phase 1: Database and tracking dashboard
- Database, models, migrations, seed script with 5 fake example businesses clearly labelled as test data.
- CSV import: name, website, phone, industry, suburb, city, rating, review_count. Ignore any email column in imports and show a notice that email addresses must be added manually (see rule 1).
- Dashboard pages (section 6).
- Manual add and edit business.
- Do-not-contact list management.
- Export all data to CSV.

#### Phase 2: Website audit and research
For each `new` business with a website, run these checks and save each as an AuditFinding with evidence:
- HTTPS enabled and no certificate errors
- Mobile viewport meta tag present
- PageSpeed Insights mobile performance score (flag below 50)
- Click-to-call `tel:` link present
- Contact form or booking link present and the form's action is not obviously broken
- Copyright year in footer (flag if 3+ years old)
- Broken links on the homepage (sample up to 20)
- Page title and meta description present
- Online booking or quote request present (relevant for services, trades, health, hospitality)
- "No solicitation" style wording (disqualify if found)
- Contact page URL and whether an email address appears to be published there. Record yes/no only, never the address.

Businesses with **no website** are also leads: mark them and skip site checks.

Then call Claude to produce the ResearchSummary from the audit findings, the page text and the business category. Prompt rules: only state what the evidence supports, mark uncertain items as uncertain, and paraphrase rather than copy text.

**Qualification score** (configurable thresholds): rating ≥ 4.0, review_count ≥ 15, at least 2 medium or high findings (or no website), not a franchise or national chain, not on the do-not-contact list, not contacted in the last 180 days. Qualified leads move on. Disqualified leads keep their reason visible.

#### Phase 3: Personalised email drafts
For each qualified business, generate a draft using the guidelines in section 7. Save as an Email with status `draft`. The review queue shows each draft beside its audit evidence so I can check every claim quickly. I can edit, regenerate with a note ("make it shorter", "focus on bookings"), approve, or discard.

#### Phase 4: Sending and reply tracking
- Approve & Send for one email at a time, via SMTP from my mailbox. Before sending, check: email address entered and confirmed as published, not on the do-not-contact list, under the daily cap, required footer and opt-out present. Block the send and explain if any check fails.
- Store the Message-ID. Thread follow-ups with In-Reply-To and References headers.
- Every 15 minutes, poll IMAP for replies. Match them by In-Reply-To or References headers first, then by sender domain. Save a Reply and classify it with Claude.
- `opt_out` or `not_interested` adds the business to the do-not-contact list immediately and cancels pending drafts. `bounce` flags the address as bad. `interested` and `question` appear at the top of the dashboard as "Needs your reply".
- Follow-up suggestions: after 5 business days without a reply, show "Follow-up available", with a draft I must approve. Only one per business.

#### Phase 5: Scheduled lead finder
- A scheduled job (default daily at a time I choose) that cycles through combinations of my target industries and locations from Settings, and calls the Google Places API Text Search, e.g. "physiotherapist in Chermside QLD".
- Pulls up to `leads_per_run` new businesses per run (default 30). Deduplicate by place_id and normalised domain, and skip anything on the do-not-contact list or already in the database.
- Saves name, category, address, phone, website, rating, review count and place_id, then queues new businesses for Phase 2 automatically.
- Tracks which industry/location combinations have been searched and when, rotating so it covers new ground each run. Revisit a combination only after 30 days.
- Log API usage and estimated cost per run, with a monthly budget limit in Settings that stops the job when reached.
- A "Run now" button on the dashboard.

### 6. Dashboard pages

- **Overview:** sent today/this week/all time, reply rate, interested replies, won clients, leads by status, today's remaining send allowance, and a "Needs your reply" list at the top.
- **Leads:** searchable, filterable table (status, industry, suburb, score, date found, last contacted, replied yes/no), with sortable columns.
- **Business detail:** all fields, audit findings with evidence, research summary, full email and reply timeline, notes, status changes, a field to enter the contact email with the "published" confirmation checkbox, and a button to mark Won or Lost.
- **Review queue:** drafts awaiting approval, one at a time, with evidence alongside, plus edit, regenerate, approve & send, or discard.
- **Replies:** all replies with classification, newest first, marked handled or not.
- **Lead finder:** schedule, target industries and locations, coverage history, last run results, API spend, Run now.
- **Do-not-contact:** the list, with reasons and dates.
- **Settings:** sender details, caps, thresholds and model name.

### 7. Email drafting guidelines (use in the drafting prompt)

- Plain text, 80–130 words, no images, no tracking pixels, no link shorteners.
- Subject: short, specific, and not clickbait, e.g. "Quick idea for [Business Name]'s website".
- Open with one specific, true observation about their business (from the research summary), not "I hope this finds you well".
- Mention 2–3 concrete website issues from the audit findings, in plain English, and say why each matters **for this type of business** (e.g. a physio losing after-hours bookings, a plumber losing mobile callers).
- No invented numbers, guarantees or competitor claims.
- One low-pressure call to action: offer a free 2-minute video walkthrough or a quick mock-up of a better homepage. Don't ask for a meeting in the first email.
- Friendly, Australian, human tone. No hype words, no exclamation marks, no fake urgency.
- Signature block with name, business name, ABN, phone and website, then the opt-out line.
- Follow-up emails: 2–3 sentences, reference the first email, offer the same thing once more, and include the opt-out line.
- If the business has no website, use the same rules but pitch getting found and contacted online.

### 8. Quality and testing

- Unit tests for deduplication, the do-not-contact check, daily cap, send pre-flight checks, reply matching and qualification scoring.
- A dry-run mode, on by default until I turn it off in Settings, where Approve & Send logs the email instead of sending it. Show a clear banner while dry-run is on.
- Graceful handling of failures: unreachable websites, API errors and rate limits. Retry with backoff, then mark the item with an error the dashboard shows. Never crash the scheduler.
- Simple logging to a file, with no secrets in the logs.
- Automatic daily backup of the SQLite database, keeping the last 14 days.

### 9. README requirements

Written for a non-developer:
- Installing Python and the project, step by step, for my operating system.
- Getting each API key (Anthropic, Google PageSpeed, Google Places) and where to put it in `.env`.
- Setting up email sending: Gmail app password and custom domain SMTP/IMAP settings, plus a short note on setting up SPF, DKIM and DMARC for an outreach domain.
- Starting the app, turning off dry-run, and the daily workflow: check replies, review drafts, send, add emails for newly qualified leads.
- A short compliance section restating the rules in section 2 in plain English.

### 10. Questions to ask me before starting

- macOS or Windows?
- My sender details: name, business name, ABN, phone, website.
- Starting industries and locations to target.
- Which email provider I'll send from.
