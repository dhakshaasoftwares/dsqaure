"""
Signed licence keys.

A key looks like  DSQ1.<payload>.<signature>  where payload is base64 JSON:

    {"v": 1, "lid": "L-0007", "licensee": "Selvam Builders", "install": "DSQ-ABCD-EFGH-JKLM",
     "issued": "2026-10-29", "expires": "2027-10-31", "users": 25, "grace": 15,
     "modules": ["attendance", "payroll", "inventory", "progress", "documents", "billing"]}

The vendor signs it with a private Ed25519 key that never leaves the vendor's
computer. Installations only hold the public key, which can check a key but
cannot create one, so a key cannot be edited (e.g. to extend the date) or
moved to another installation.
"""

import base64
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from django.conf import settings
from django.utils.translation import gettext_lazy as _

PREFIX = "DSQ1"
ALL_MODULES = ["attendance", "payroll", "inventory", "progress", "documents", "billing"]


class LicenceError(Exception):
    pass


def _b64e(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass
class Licence:
    licence_id: str
    licensee: str
    install_id: str
    issued: date
    expires: date
    max_users: int
    grace_days: int
    modules: list = field(default_factory=list)

    def to_payload(self):
        return {"v": 1, "lid": self.licence_id, "licensee": self.licensee, "install": self.install_id,
                "issued": self.issued.isoformat(), "expires": self.expires.isoformat(), "users": self.max_users,
                "grace": self.grace_days, "modules": self.modules}

    @classmethod
    def from_payload(cls, data):
        try:
            return cls(
                licence_id=str(data["lid"]), licensee=str(data["licensee"]), install_id=str(data["install"]),
                issued=date.fromisoformat(data["issued"]), expires=date.fromisoformat(data["expires"]),
                max_users=int(data["users"]), grace_days=int(data.get("grace", 0)),
                modules=[m for m in data.get("modules", ALL_MODULES) if m in ALL_MODULES],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LicenceError(_("The licence key is damaged.")) from exc


# --- Keys -------------------------------------------------------------------

def public_key_file():
    return Path(getattr(settings, "LICENCE_PUBLIC_KEY_FILE",
                        Path(__file__).resolve().parent / "vendor_public_key.txt"))


_cache = {}


def load_public_key():
    """The vendor's public key, or None when licensing has not been set up yet."""
    path = public_key_file()
    try:
        stamp = (str(path), path.stat().st_mtime)
    except FileNotFoundError:
        return None
    if stamp not in _cache:
        text = path.read_text().strip()
        _cache.clear()
        _cache[stamp] = Ed25519PublicKey.from_public_bytes(_b64d(text)) if text else None
    return _cache[stamp]


def generate_keypair():
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption())
    public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private_pem, _b64e(public_raw)


def load_private_key(path):
    return serialization.load_pem_private_key(Path(path).read_bytes(), password=None)


# --- Sign / verify -----------------------------------------------------------

def sign(licence, private_key):
    payload = json.dumps(licence.to_payload(), separators=(",", ":"), sort_keys=True).encode()
    signature = private_key.sign(payload)
    return f"{PREFIX}.{_b64e(payload)}.{_b64e(signature)}"


def verify(key_text, public_key):
    key_text = "".join((key_text or "").split())  # tolerate line breaks from email / WhatsApp
    parts = key_text.split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise LicenceError(_("This is not a DSquare licence key."))
    try:
        payload, signature = _b64d(parts[1]), _b64d(parts[2])
    except ValueError as exc:
        raise LicenceError(_("The licence key is damaged.")) from exc
    try:
        public_key.verify(signature, payload)
    except InvalidSignature as exc:
        raise LicenceError(_("The licence key is not genuine or has been changed.")) from exc
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise LicenceError(_("The licence key is damaged.")) from exc
    return Licence.from_payload(data)
