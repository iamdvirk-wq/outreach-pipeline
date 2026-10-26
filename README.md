# Outreach Pipeline

A small app that runs on your own computer and helps you find local businesses
that could use a better website, research them, write a personalised email
for you to check, and keep track of who you've contacted and who replied.

Nothing is ever emailed without you pressing **Approve & Send** on that one
email. The rules that keep you inside the Spam Act are built into the app; see
[the compliance section](#the-rules-in-plain-english).

## Build progress

| Phase | What it adds | Status |
|---|---|---|
| 1 | Database, dashboard, add/edit businesses, CSV import, do-not-contact list, export | **Done** |
| 2 | Website audit and AI research summary | Next |
| 3 | Personalised email drafts | |
| 4 | Sending (with all safety checks) and reply tracking | |
| 5 | Scheduled lead finder (Google Places) | |

Pages for later phases already exist but show a "coming in Phase X" note.

---

## Step 1: Install Python (one time)

You need **Python 3.11 or newer**.

**Mac**
1. Go to <https://www.python.org/downloads/macos/> and download the latest
   "macOS 64-bit universal2 installer" for Python 3.13.
2. Open the downloaded file and click through the installer.
3. When it finishes, a Finder window opens. Double-click
   **Install Certificates.command** in it.

**Windows**
1. Go to <https://www.python.org/downloads/windows/> and download the latest
   "Windows installer (64-bit)" for Python 3.13.
2. Run it. On the first screen **tick "Add python.exe to PATH"**, then click
   **Install Now**.

## Step 2: Get the code (one time)

The easiest way is **GitHub Desktop** (free, Mac and Windows):

1. Install it from <https://desktop.github.com> and sign in with your GitHub account.
2. **File → Clone repository**, pick `outreach-pipeline`, choose a folder, click **Clone**.

When a new phase is ready, open GitHub Desktop and click **Fetch origin**, then
**Pull origin**. That's how you get updates.

## Step 3: Start the app

**Mac**
1. Open **Terminal** (press ⌘ Space, type *Terminal*, press Enter).
2. Type `cd ` (with a space), drag the `outreach-pipeline` folder onto the
   Terminal window, and press Enter.
3. Type `./start.sh` and press Enter.

**Windows**
- Open the `outreach-pipeline` folder and double-click **start.bat**.

The first start takes a minute while it installs what it needs. Then your
browser opens at **<http://localhost:8000>**. Keep the Terminal / black window
open while you use the dashboard. Close it, or press Ctrl+C, to stop the app.

The dashboard only works on your own computer. Nobody else on the internet
or your Wi-Fi can open it.

### Try it with example data

To see the dashboard with a few fake businesses, stop the app and run this
once in the same folder:

- Mac: `.venv/bin/python -m scripts.seed`
- Windows (Command Prompt in the folder): `.venv\Scripts\python -m scripts.seed`

Then start the app again. The examples are marked **TEST** and use made-up
`.example` web addresses. Remove them with **Delete test data** on the
Overview page when you're done.

## Step 4: Fill in your details

Open **Settings** in the dashboard and enter your name, business name, ABN,
phone and website. These go at the bottom of every email, as the Spam Act
requires. Add the industries and locations you want to target too.

**Dry-run mode** is on to start with. While it's on, Approve & Send only
records the email instead of sending it, and a yellow banner shows at the top
of every page. Turn it off in Settings once you've tested everything (from
Phase 4). You can't turn it off until your sender details are filled in.

---

## API keys and passwords (the `.env` file)

Secrets go in a file called `.env` in the project folder. It's created for
you on first start (a copy of `.env.example`). Open it in TextEdit (Mac) or
Notepad (Windows), paste each value after the `=`, save, and restart the app.
`.env` is never uploaded to GitHub and keys are never written to the logs.

You don't need any keys for Phase 1.

| Setting | Needed from | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Phase 2 | <https://console.anthropic.com> → **API Keys** → **Create Key**. Add a little credit under **Billing**. |
| `CLAUDE_MODEL` | Phase 2 | Already set to `claude-sonnet-5-5`. Check the current model names at <https://docs.anthropic.com/en/docs/about-claude/models>. You can also change it in Settings. |
| `GOOGLE_PAGESPEED_API_KEY` | Phase 2 | <https://console.cloud.google.com> → create a project → **APIs & Services → Library** → enable **PageSpeed Insights API** → **Credentials → Create credentials → API key**. |
| `GOOGLE_PLACES_API_KEY` | Phase 5 | Same Google project: enable **Places API (New)** and set up billing. You can use the same key as PageSpeed. Restrict the key to those two APIs. |
| `SMTP_…` / `IMAP_…` | Phase 4 | See below. |
| `TIMEZONE` | now | Your city, e.g. `Australia/Brisbane`. Used to work out "today" for the daily send cap. |

## Setting up email (needed from Phase 4)

### Gmail or Google Workspace

The app signs in with an **App Password**, a separate 16-character password
just for this app. You can revoke it any time.

1. Turn on 2-Step Verification: <https://myaccount.google.com/signinoptions/twosv>
2. Create an App Password: <https://myaccount.google.com/apppasswords>. Name it
   "Outreach" and copy the 16 letters (no spaces).
3. In `.env`:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=you@yourdomain.com.au
   SMTP_PASSWORD=abcdabcdabcdabcd
   IMAP_HOST=imap.gmail.com
   IMAP_PORT=993
   IMAP_USER=you@yourdomain.com.au
   IMAP_PASSWORD=abcdabcdabcdabcd
   ```
4. On Google Workspace, if the App Passwords page says it isn't available, an
   admin needs to allow 2-Step Verification for your account in the Google
   Admin console (**Security → Authentication → 2-Step Verification**).

### Other mailboxes (cPanel, Zoho, Fastmail, Outlook…)

Your provider's help pages list the "SMTP" and "IMAP" server names. Use port
587 for SMTP and 993 for IMAP, with your full email address as the user.
Outlook / Microsoft 365 is `smtp.office365.com` and `outlook.office365.com`.

### Protect your main domain: SPF, DKIM and DMARC

Cold email can hurt your domain's reputation, so consider a **separate outreach
domain** (e.g. `getyourname.com.au` alongside `yourname.com.au`) with its own
mailbox. Whichever domain you send from, set up these three DNS records at your
domain registrar. Your email provider's help pages give the exact values.

- **SPF** says which servers may send for your domain (for Google:
  `v=spf1 include:_spf.google.com ~all`).
- **DKIM** adds a signature proving the email really came from you. Turn it on
  in your email provider's admin panel, then paste the record it gives you into DNS.
- **DMARC** tells receivers what to do with emails that fail the two checks
  above. Start with `v=DMARC1; p=none; rua=mailto:you@yourdomain.com.au`.

Warm up a new domain slowly: a handful of emails a day for the first couple of
weeks, well under the daily cap.

---

## Daily workflow

1. **Overview**: check **Needs your reply** first and answer interested people
   from your normal mailbox. Mark each reply handled on the **Replies** page.
2. **Leads**: for newly qualified businesses, open each one, find the email
   address published on **their own website or listing**, type it into
   **Contact email**, and tick the confirmation box.
3. **Review queue**: read each draft beside its evidence, edit if needed, then
   approve and send (from Phase 4).
4. When a deal closes, open the business and press **Mark Won** or **Mark Lost**.

## Your data

Everything stays on your computer, in the project folder:

| What | Where |
|---|---|
| Database | `data/outreach.db` |
| Daily backups (newest 14 kept) | `data/backups/` |
| Do-not-contact list (permanent copy) | `suppression/do_not_contact.csv` |
| Log file | `logs/app.log` |

- **Export:** Overview → **Export all data** downloads a zip with one CSV per
  table. Leads → **Export CSV** downloads just the businesses.
- **Import:** Leads → **Import CSV**. Only use lists you collected yourself.
  Email columns are always ignored.
- **Start over:** stop the app, then run `.venv/bin/python -m scripts.reset_db`
  (Windows: `.venv\Scripts\python -m scripts.reset_db`). It backs up first, and
  the do-not-contact list is kept.
- Back up the whole folder (except `.venv`) to cloud storage now and then.

## The rules in plain English

The app is built to keep you on the right side of Australia's **Spam Act 2003**.
These rules are enforced in the code, not just written down here.

1. **No address harvesting.** The app never collects email addresses from
   websites, Google or directories, and never imports them from a file. You type
   each address yourself and tick a box confirming you found it published on
   the business's own website or listing.
2. **You approve every email.** No bulk send, no automatic sending, no
   automatic follow-ups.
3. **Daily limit.** 20 a day by default; you can change it, but never above 50.
   Sends are at least 3 minutes apart.
4. **Every email says who you are and how to opt out.** Your name, business
   name, ABN, phone and website, plus a line like "If you'd rather not hear from
   me, just reply 'no thanks' and I won't contact you again." Opt-out replies
   are actioned automatically, well within the 5 business days the Act allows.
5. **Do-not-contact list.** Anyone who opts out, says no, or that you add
   by hand is blocked for good, by website domain and email address. Opt-outs
   can't be removed. The list is kept in a separate file so it survives a
   database reset, and it's in every backup.
6. **No pestering.** At most one follow-up, at least 5 business days after the
   first email, and only if you approve it. After that, the same business isn't
   contacted again for at least 180 days.
7. **Businesses that say "no solicitations" are skipped.**
8. **Only true claims.** Every website problem mentioned in an email must come
   from a recorded check with evidence. Nothing is made up.
9. **Lead sources follow their terms.** The official Google Places API (no
   scraping of Google Maps), or CSV files you collected yourself.
10. **Polite website checks.** The app respects robots.txt, identifies
    itself, waits between requests, and only looks at a few pages per site.
11. **Secrets stay secret.** Keys and passwords live only in `.env`.

This is a summary to help you work safely, not legal advice. The ACMA's guide
for businesses is at <https://www.acma.gov.au/avoid-sending-spam>.

## Troubleshooting

- **"Python 3.11 or newer is needed"**: install Python (Step 1). On Windows,
  re-run the installer, choose **Modify**, and make sure "Add to PATH" is ticked.
- **Mac: "permission denied" for `./start.sh`**: run `chmod +x start.sh` once.
- **"Address already in use"**: the app is already running in another window,
  or another program uses port 8000. Close the other window, or add `PORT=8001`
  to `.env` and open <http://localhost:8001>.
- **Something went wrong on a page**: look at the end of `logs/app.log`.

## For developers

```
.venv/bin/python -m pytest        # run the tests
```

- `app/models.py`: database tables. After changing them, create a migration
  with `.venv/bin/alembic revision --autogenerate -m "what changed"`.
  Migrations run automatically when the app starts.
- `app/routes/`: the dashboard pages; `app/templates/`: the HTML (Jinja2 + HTMX).
- `app/dnc.py`: the do-not-contact list; `app/csv_import.py`: CSV import.
- `BUILD_BRIEF.md`: the full specification for all phases.
