"""
Vendor tool – run on YOUR computer, never on a client's.

  1. Once:  python manage.py licence keygen
            creates your private signing key (keep it secret, back it up) and
            writes the matching public key into the app, which you commit.

  2. Per client / renewal:
            python manage.py licence issue --install DSQ-ABCD-EFGH-JKLM \\
                --licensee "Selvam Builders" --expires 2027-10-31 --users 25
            prints the licence key to send to the client.

  3. Check any key:  python manage.py licence show <key>
"""

import os
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.licensing import keys

DEFAULT_PRIVATE = Path.home() / ".dsquare" / "licence_private_key.pem"


class Command(BaseCommand):
    help = "Create signing keys and issue licence keys (vendor only)"

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        kg = sub.add_parser("keygen", help="create your signing key pair (once)")
        kg.add_argument("--private-key", default=str(DEFAULT_PRIVATE))
        kg.add_argument("--force", action="store_true", help="replace existing keys (old licences stop working)")

        iss = sub.add_parser("issue", help="issue a licence key")
        iss.add_argument("--private-key", default=str(DEFAULT_PRIVATE))
        iss.add_argument("--install", required=True, help="installation ID shown on the client's Licence page")
        iss.add_argument("--licensee", required=True, help="client company name")
        iss.add_argument("--expires", required=True, help="YYYY-MM-DD")
        iss.add_argument("--users", type=int, default=25)
        iss.add_argument("--grace", type=int, default=15, help="days the app keeps working after expiry")
        iss.add_argument("--modules", default="all",
                         help="comma list of " + ",".join(keys.ALL_MODULES) + " or 'all'")
        iss.add_argument("--id", default="", help="your reference, e.g. invoice number")

        show = sub.add_parser("show", help="check and print a licence key")
        show.add_argument("key")

    def handle(self, *args, action, **opts):
        getattr(self, action)(**opts)

    def keygen(self, private_key, force, **_):
        private_path = Path(private_key).expanduser()
        public_path = keys.public_key_file()
        if (private_path.exists() or public_path.exists()) and not force:
            raise CommandError(f"Keys already exist ({private_path} / {public_path}). "
                               "Use --force only if you really want new keys: every existing licence will stop working.")
        pem, public = keys.generate_keypair()
        private_path.parent.mkdir(parents=True, exist_ok=True)
        private_path.write_bytes(pem)
        os.chmod(private_path, 0o600)
        public_path.write_text(public + "\n")
        self.stdout.write(self.style.SUCCESS(f"Private key: {private_path}  (KEEP SECRET, back it up offline)"))
        self.stdout.write(f"Public key written to {public_path} – commit this file so every install can check keys.")

    def issue(self, private_key, install, licensee, expires, users, grace, modules, id, **_):
        path = Path(private_key).expanduser()
        if not path.exists():
            raise CommandError(f"No private key at {path}. Run 'licence keygen' first.")
        mods = keys.ALL_MODULES if modules == "all" else [m.strip() for m in modules.split(",") if m.strip()]
        unknown = set(mods) - set(keys.ALL_MODULES)
        if unknown:
            raise CommandError(f"Unknown modules: {', '.join(sorted(unknown))}")
        try:
            expiry = date.fromisoformat(expires)
        except ValueError:
            raise CommandError("--expires must look like 2027-10-31")
        today = timezone.localdate()
        licence = keys.Licence(licence_id=id or f"L-{today:%Y%m%d}-{install[-4:]}", licensee=licensee,
                               install_id=install.strip().upper(), issued=today, expires=expiry,
                               max_users=users, grace_days=grace, modules=mods)
        key = keys.sign(licence, keys.load_private_key(path))
        self.stdout.write(f"Licence for {licensee} ({install}) until {expiry}, {users} users, modules: {', '.join(mods)}\n")
        self.stdout.write(key)

    def show(self, key, **_):
        public = keys.load_public_key()
        if public is None:
            raise CommandError("No public key in this app. Run 'licence keygen' first.")
        try:
            licence = keys.verify(key, public)
        except keys.LicenceError as exc:
            raise CommandError(str(exc))
        for k, v in licence.to_payload().items():
            self.stdout.write(f"{k:10} {v}")
