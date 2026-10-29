# DSquare – Construction Management

A complete, self-hosted web app for construction companies: sites, staff, attendance, salary,
purchase and stock, building progress, quotations and agreements. It is used from **any phone or
computer** through a web link and can be installed on a phone like an app (PWA).

It is built as a **product**: one codebase, deployed separately for each client company and
configured from screens, with no code changes per client.

* **Configuration-driven**: company profile, logo, brand colour, time zone, financial year, modules,
  currency, number format (international or Indian lakh), tax name and rates, PF/ESI/other pay rules,
  document numbering, units, stages, rate lists, agreement wording, roles and permissions are all
  set in the app.
* **One installation per client**: each client gets its own database and photo storage, so data can
  never mix. One laptop or server can run many clients side by side.
* **English + தமிழ்**: each user picks their language. Printed PDFs support Tamil text.
* **Proprietary**: see `LICENSE`. Keep this repository private.

## Modules

| Module | What it does |
|--------|--------------|
| **Projects / sites** | Site list, client, contract value, GPS location, one dashboard per site with progress, material, labour and documents |
| **Attendance** | Phone check-in with GPS + photo inside the site radius, supervisor marks a whole site at once, monthly register |
| **Employees** | Daily-wage and monthly staff, wages, bank/UPI, ID proof, assigned site, login account |
| **Salary** | Pay from attendance, overtime, configurable allowances/deductions (PF, ESI, PT …), advances with instalments, payslips, bank sheet |
| **Inventory** | Materials, suppliers, godowns + automatic site stores, purchase orders with approval, goods receipt against PO (partial deliveries), transfers between sites, material used at site, opening stock/adjustments, stock ledger, low-stock alerts, PO PDF |
| **Building progress** | Company standard stages with weights, stage % and planned/actual dates, daily updates with site photos (auto-compressed), delayed-stage alerts, client progress report PDF |
| **Quotations** | Clients, rate library, quotation with discount and tax, revisions, status, branded PDF |
| **Agreements** | Your own agreement templates with placeholders, payment milestones, generated from a quotation, editable wording, PDF with signature blocks |
| **Client billing** | Running bills raised from the agreement's payment milestones (or for extra work), CGST/SGST or IGST (or any tax names), retention, gap-free invoice numbers on issue, payments received (bank/UPI/cheque/cash), billing statement per agreement, overdue alerts, tax invoice PDF with amount in words |
| **Send documents** | Email with the PDF attached (each client's own email account), WhatsApp with a secure expiring link, or "Share PDF" from the phone straight into WhatsApp; log of what was sent |
| **Licence** | Signed licence key per installation with expiry, grace period, user limit and licensed modules; read-only when expired |
| **Users & roles** | Tick-box permissions per module (view/add/edit/delete + special ones like "approve purchase orders") |
| **Security** | Account lock after repeated wrong passwords, uploaded files visible only to permitted roles, audit log of every change |

## Licensing your clients (you, the vendor)

Licence keys are signed with **your private key**, which stays on your computer. Installations only
contain the matching public key, so keys cannot be edited (e.g. to extend the date or add users) or
reused on another installation.

**Once (on your own computer, in this repository):**
```bash
python manage.py licence keygen
```
This creates `~/.dsquare/licence_private_key.pem`. **Keep it secret and back it up offline**: if you
lose it you cannot issue renewals, and if someone else gets it they can make keys. It also writes
`apps/licensing/vendor_public_key.txt`: commit that file and deploy it to every client.

**For each client / renewal:**
1. The client opens **Licence** in the menu and sends you their **Installation ID** (e.g. `DSQ-ABCD-EFGH-JKLM`).
2. You run:
   ```bash
   python manage.py licence issue --install DSQ-ABCD-EFGH-JKLM --licensee "Selvam Builders" \
       --expires 2027-10-31 --users 25 --modules all --grace 15
   ```
   (`--modules` can be a list, e.g. `attendance,payroll,progress` for a cheaper plan.)
3. Send the printed key by WhatsApp/email; the owner pastes it on the Licence page.

**What the client sees:** a new installation runs as a 30-day trial (10 users). The owner is
reminded from 30 days before expiry, then after expiry the grace days give a red warning. After that
the app becomes **read-only**: everything can be viewed and printed, nothing can be added, until a new
key is entered. Turning the computer clock back does not help.

Be realistic: when the software runs on the client's own computer, a determined programmer could
remove the check from the code. The licence, together with the LICENSE file and your written
agreement with the client, makes copying clearly illegal and inconvenient. Hosting the client
yourself (only giving them a link) is the strongest protection.

## Tech stack (all free & open source)

Python · Django 5.2 LTS · PostgreSQL · WeasyPrint (PDF) · plain HTML/CSS/JS (no build step) · Docker · Cloudflare Tunnel.

```
apps/
  core/        company settings, modules, numbering, audit log, setup wizard, projects, dashboards
  accounts/    login + lockout, users, roles & permissions, language
  employees/   staff records
  attendance/  check-in / check-out, supervisor marking, register
  payroll/     pay rules, advances, payroll runs, payslips (services.py = salary engine)
  inventory/   materials, suppliers, POs, receipts, transfers, issues, stock ledger (services.py = stock rules)
  progress/    stages, updates, site photos, progress report
  documents/   clients, rate items, quotations, agreement templates, agreements
  billing/     invoices, payments received, agreement statements (services.py = billing rules)
  sharing/     email / WhatsApp / share links
  licensing/   installation ID, licence check, vendor 'licence' command
templates/     all screens and PDF layouts
locale/ta/     Tamil translations
scripts/       new_client.sh (new client install), backup.sh
```

---

## Installing for a client

**Needed:** a Windows 10/11, Mac or Linux computer (or a cloud server) with internet access, and
[Docker Desktop](https://www.docker.com/products/docker-desktop/) (free for small businesses).

### One client on one machine

```bash
git clone https://github.com/dhakshaasoftwares/dsqaure.git
cd dsqaure
cp .env.example .env          # then set SECRET_KEY and POSTGRES_PASSWORD to long random values
docker compose up -d --build
```

Open **http://localhost:8000**. On a brand-new install the **setup wizard** asks for the company
name, country preset (India = INR, GST, Indian number format, sample PF/ESI rules switched off) and
the owner's login. After that, go to **Settings & configuration** and set the rest.

### Several clients on one machine

```bash
scripts/new_client.sh selvam-builders 8001 selvam.yourdomain.com
scripts/new_client.sh sri-homes       8002 srihomes.yourdomain.com
```

Each command creates `clients/<name>/.env` with its own random passwords, its own database and
photo storage, and starts it on its own port. Open `http://localhost:8001` to run that client's
setup wizard. Keep the `clients/` folder safe: it holds each client's passwords. It is never committed.

### Demo data (for showing the product)

On an **empty** install: `docker compose exec web python manage.py load_demo --password <pick-one>`
loads two sites, staff, attendance, stock, a PO, a quotation and an agreement.

### Make it reachable from anywhere: Cloudflare Tunnel (free)

1. Add your domain to a free Cloudflare account. A domain costs about ₹800/year; this is the only cost.
2. **Zero Trust → Networks → Tunnels → Create tunnel**, and copy the token.
3. Add a public hostname per client, e.g. `selvam.yourdomain.com` → `http://localhost:8001`
   (for the single-client compose setup use `http://web:8000` and put the token in `.env` as
   `CLOUDFLARE_TUNNEL_TOKEN`, then `docker compose --profile tunnel up -d`).
4. In that client's `.env`, set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` to the hostname.
   When everyone uses the `https://` address, also set `SECURE_COOKIES=True`.

### Install on phones

Open the `https://` address in **Chrome (Android)** → menu → **Install app / Add to Home screen**,
or in **Safari (iPhone)** → Share → **Add to Home Screen**. GPS check-in and the camera need https.

### Backups (do not skip)

```bash
scripts/backup.sh                    # single-client install
scripts/backup.sh selvam-builders    # a client created with new_client.sh
```
This writes `backups/<client>/db_*.sql.gz` and `media_*.tar.gz` and keeps 30 days. Schedule it
nightly (Linux/Mac `crontab -e`; Windows Task Scheduler via WSL/Git Bash) and copy `backups/` off the
machine, e.g. with [rclone](https://rclone.org) to Google Drive: `rclone copy backups gdrive:dsquare-backups`.

**Restore:** `gunzip -c backups/<client>/db_XXXX.sql.gz | docker compose -p <client> --env-file clients/<client>/.env exec -T db psql -U dsquare dsquare`

### Updating every client to a new version

```bash
git pull
docker compose up -d --build                                                     # single client
ENV_FILE=clients/<name>/.env docker compose -p <name> --env-file clients/<name>/.env up -d --build   # each client
```
Database changes and new default settings are applied automatically on start.

---

## Setting up a new client (inside the app)

1. **Setup wizard**: company name, country preset, owner login.
2. **Settings & configuration → Company settings**: logo, brand colour, address, modules in use,
   tax, number format, document footer/signatory, salary rules, check-in rules, lockout.
3. **Document numbering**: e.g. `PO/{FY}/{SEQ}` → `PO/2026-27/0001` (restarts each financial year).
4. **Roles & permissions** and **Users**: default roles are Admin, Site Supervisor, Accountant,
   Storekeeper, Sales / Estimator and Employee. Change the ticks or add roles.
5. **Masters**: units, material categories, materials (with reorder levels), suppliers, godowns,
   standard stages, rate items, agreement template, pay rules.
6. **Projects**: add sites; each gets a stock location automatically. Tap *Use my current location*
   on site so GPS check-in works.
7. **Opening stock**: Inventory → Adjustments → reason "Opening stock", with rates.

### Sending documents

* **Email:** in Company settings → Email & WhatsApp, enter the client company's email server.
  For Gmail: server `smtp.gmail.com`, port 587, TLS on, and an *app password*
  (Google Account → Security → App passwords). The password is stored encrypted.
* **WhatsApp:** no setup needed. *Share PDF* (on a phone) sends the PDF file itself; *Open WhatsApp*
  sends a secure link that works for the configured number of days and can be stopped at any time.
* Message wording uses placeholders: `{client} {document} {number} {amount} {company} {link}`.

### Daily use

* **Workers**: check in/out from their phone.
* **Supervisors**: mark site attendance, record material used, post progress updates with photos.
* **Storekeeper**: raise POs → owner approves → receive goods (partial deliveries supported) → transfer to sites.
* **Office**: payroll, quotations → agreement → PDFs, client progress reports.
* **Accounts**: agreement → *Billing statement* → *Raise bill* for each completed milestone → Issue →
  send by WhatsApp/email → record payments when they arrive.

### How salary is calculated

* **Daily wage:** days worked × daily rate (half day = 0.5).
* **Monthly:** salary ÷ basis days × paid days (basis is calendar days, working days or 30; paid
  leave, holidays and weekly offs follow settings).
* **Overtime:** OT hours × (per-day rate ÷ working hours × multiplier), or the employee's own OT rate.
* **Pay rules:** earnings are added first, then deductions and employer contributions.
* **Advances:** recovered oldest first, in instalments if set, and never below zero net pay.

### How stock works

Every receipt, transfer, issue and adjustment writes to a stock ledger. Stock at a location is the
sum of its ledger. Stock cannot go below zero unless the company setting allows it. Deleting a
document reverses its ledger entries, but only if that stock has not been used since. Stock value
uses the last purchase rate.

---

## For developers

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # WeasyPrint needs Pango (apt: libpango-1.0-0 libpangoft2-1.0-0)
python manage.py migrate
python manage.py runserver               # open /setup/ to create the company and owner
python manage.py load_demo               # optional sample data
python manage.py test                    # 117 tests
```
Without `DATABASE_URL` it uses SQLite. Add a configurable list with `apps/core/crud.py` (one line per
screen). Translations: `python manage.py makemessages -l ta`, edit `locale/ta/LC_MESSAGES/django.po`,
`python manage.py compilemessages`. If WeasyPrint is not installed, PDF links open a printable page instead.
