# DSquare – Construction Management

A self-hosted web app for a small construction company. It runs on **one laptop or desktop**
and is used from **any phone or computer** through a normal web link. It can also be
installed on a phone like an app (PWA), with no Play Store / App Store needed.

* **You own everything**: the code (this repo), the server (your laptop), the data (your database).
  There are no subscriptions and no vendor lock-in.
* **Configuration-driven**: currency, tax name/rate, PF / ESI / social security, overtime rules,
  weekly off, salary basis and roles are all set from screens. None of it is hard-coded,
  so any company in any country can adapt it.
* **English + தமிழ்**: each user picks their language.

## Modules

| # | Module | Status |
|---|--------|--------|
| 1 | Attendance: phone check-in with GPS + selfie, supervisor bulk marking, monthly register | ✅ Done |
| 2 | Employee management: daily / monthly staff, wages, bank / UPI, ID proof, site assignment | ✅ Done |
| 3 | Salary: attendance → wages, overtime, configurable allowances/deductions, advances, payslips, bank sheet | ✅ Done |
| 7 | Users, roles & permissions screen (tick boxes per module) | ✅ Done |
| 8 | Mobile-first PWA, usable from anywhere | ✅ Done |
| 4 | Inventory: suppliers, purchase orders, goods receipt, stock per site, transfers | ⏳ Next |
| 5 | Building progress: stages, % complete, site photos | ⏳ Planned |
| 6 | Quotation & agreement generator (PDF) | ⏳ Planned |

## Tech stack (all free & open source)

Python · Django 5.2 LTS · PostgreSQL · plain HTML/CSS (no build step) · Docker · Cloudflare Tunnel.

```
apps/
  accounts/    login, users, roles & permissions, language
  core/        company settings, projects/sites, dashboard
  employees/   employee records
  attendance/  check-in / check-out, supervisor marking, register
  payroll/     pay rules, advances, payroll runs, payslips (services.py = salary engine)
templates/     all screens
locale/ta/     Tamil translations (edit django.po, then run compilemessages)
```

---

## Install on your laptop / desktop (one time, about 30 minutes)

**What you need:** a Windows 10/11, Mac or Linux computer that stays on during working hours, and internet.

1. **Install Docker Desktop**: https://www.docker.com/products/docker-desktop/ (free for small businesses).
   On Windows, allow it to enable WSL 2 when asked, then restart.
2. **Download this project**: install Git (https://git-scm.com), then in a terminal:
   ```bash
   git clone https://github.com/dhakshaasoftwares/dsqaure.git
   cd dsqaure
   ```
3. **Create your settings file**: copy `.env.example` to `.env` and change `SECRET_KEY` and
   `POSTGRES_PASSWORD` to long random values.
4. **Start the app**:
   ```bash
   docker compose up -d --build
   ```
5. **Create the owner login** (the owner can always do everything):
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```
6. Open **http://localhost:8000** and log in. Phones on the **same Wi-Fi** can use
   `http://<laptop-ip>:8000` (add that IP to `ALLOWED_HOSTS` in `.env`).

Optional: load sample Indian pay rules (PF, ESI, professional tax, food allowance). They are
added **switched off**, so check the current rates and switch on only what applies to you:
```bash
docker compose exec web python manage.py setup_defaults --preset india
```

### Make it reachable from anywhere (free): Cloudflare Tunnel

This gives you a secure `https://` address without a static IP or opening router ports.

1. Create a free Cloudflare account and add a domain. A `.in` / `.com` domain costs about ₹800/year;
   this is the only cost.
2. In Cloudflare **Zero Trust → Networks → Tunnels → Create tunnel** (type *Cloudflared*), copy the **token**.
3. Under *Public hostname*, add e.g. `app.yourdomain.com` → service **`http://web:8000`**.
4. Put the token in `.env` as `CLOUDFLARE_TUNNEL_TOKEN=...`, and set
   `ALLOWED_HOSTS=app.yourdomain.com,localhost` and `CSRF_TRUSTED_ORIGINS=https://app.yourdomain.com`.
5. Start with the tunnel:
   ```bash
   docker compose --profile tunnel up -d
   ```

### Install on phones

Open `https://app.yourdomain.com` in **Chrome (Android)** → menu → **Add to Home screen / Install app**.
On **iPhone (Safari)** → Share → **Add to Home Screen**. GPS and camera need the `https://` address.

### Backups (do not skip)

```bash
scripts/backup.sh          # writes backups/db_*.sql.gz and backups/media_*.tar.gz
```
Schedule it nightly (Linux/Mac: `crontab -e` → `0 2 * * * /path/to/dsqaure/scripts/backup.sh`;
Windows: Task Scheduler running it through Git Bash or WSL). Then copy the `backups` folder off
the laptop for free with [rclone](https://rclone.org) to Google Drive:
`rclone copy backups gdrive:dsquare-backups`.

**Restore:** `gunzip -c backups/db_XXXX.sql.gz | docker compose exec -T db psql -U dsquare dsquare`

### Updating to a new version

```bash
git pull
docker compose up -d --build     # database changes are applied automatically
```

### Moving to a cloud server later

The same `docker compose` setup runs unchanged on any Linux server (e.g. Oracle Cloud *Always Free*).
Restore your latest backup there and point the Cloudflare tunnel at it.

---

## First-day setup inside the app

1. **Company settings**: name, logo, currency, tax, working hours, overtime multiplier,
   weekly off, monthly salary basis, check-in rules (GPS radius / photo).
2. **Projects / sites**: add each site. Stand at the site and tap *Use my current location*
   so GPS check-in works.
3. **Pay rules**: add only what applies (PF, ESI, allowances, professional tax, social security…).
   Each rule is a fixed amount, an amount per day, or a % of wage / gross, with optional ceiling and
   eligibility limit. Mark it *apply to everyone*, or tick it per employee.
4. **Roles & permissions**: default roles are Admin, Site Supervisor, Accountant, Storekeeper and Employee.
   Change the tick boxes or create your own.
5. **Employees**: add staff with wage type and rate. To let someone check in from their own phone,
   create a **User** for them and select it as the employee's *login account*.
6. **Daily**: workers check in from their phones, *or* the supervisor uses **Mark site attendance**
   for the whole site (for workers without smartphones).
7. **Payroll**: *New payroll* → choose period → review → **Finalize** → download the bank sheet / print payslips.

### How salary is calculated

* **Daily wage:** `days worked × daily rate` (half day = 0.5).
* **Monthly:** `monthly salary ÷ basis days × paid days`. The basis is calendar days, working days or a
  fixed 30, chosen in settings. Paid leave, holidays and weekly offs are paid according to settings.
* **Overtime:** `OT hours × (per-day rate ÷ working hours × multiplier)`, or the employee's own OT rate.
* **Pay rules:** earnings are added first, then deductions and employer contributions are worked out.
* **Advances:** recovered oldest first, in instalments if set, never taking net pay below zero. They are
  only marked recovered when the payroll is finalized.

---

## For developers

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py setup_defaults
python manage.py createsuperuser
python manage.py runserver
python manage.py test               # 33 tests
```
Without `DATABASE_URL` it uses SQLite for quick local trials. Translations: `python manage.py
makemessages -l ta`, edit `locale/ta/LC_MESSAGES/django.po`, `python manage.py compilemessages`.
