import base64
import hashlib
import re
from datetime import timedelta
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.numbers import format_money
from apps.core.pdf import HTML

from .models import SentMessage, ShareLink
from .registry import DOC_TYPES


class SendError(Exception):
    pass


# --- Stored email password -------------------------------------------------

def _fernet():
    key = base64.urlsafe_b64encode(hashlib.sha256(("dsquare-smtp:" + settings.SECRET_KEY).encode()).digest())
    return Fernet(key)


def encrypt_secret(plain):
    return "enc:" + _fernet().encrypt(plain.encode()).decode() if plain else ""


def decrypt_secret(stored):
    if not stored:
        return ""
    if not stored.startswith("enc:"):
        return stored
    try:
        return _fernet().decrypt(stored[4:].encode()).decode()
    except InvalidToken:
        return ""  # SECRET_KEY changed – the password has to be entered again


# --- PDF -----------------------------------------------------------------

def render_pdf(doc_type, obj, company):
    template, context = DOC_TYPES[doc_type].pdf(obj, company)
    html = render_to_string(template, {**context, "company": company, "pdf": HTML is not None})
    if HTML is None:
        return None, html
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf(), html


def filename_for(doc_type, obj):
    number = DOC_TYPES[doc_type].number(obj) or f"{doc_type}-{obj.pk}"
    return re.sub(r"[^\w.-]+", "-", f"{DOC_TYPES[doc_type].title}-{number}") + ".pdf"


# --- Messages --------------------------------------------------------------

def placeholders(doc_type, obj, company, link=""):
    d = DOC_TYPES[doc_type]
    name, _email, _phone = d.recipient(obj)
    amount = d.amount(obj, company)
    return {
        "company": company.name, "document": str(d.title), "number": d.number(obj), "client": name,
        "link": link, "amount": f"{company.currency_symbol}{format_money(amount)}" if amount is not None else "",
    }


def fill(template, values):
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), template or "")


def whatsapp_number(phone, country_code):
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits.lstrip("0")
        digits = f"{country_code}{digits}" if country_code else digits
    elif country_code and len(digits) <= 10:
        digits = f"{country_code}{digits}"
    return digits


def whatsapp_url(phone, text, country_code):
    number = whatsapp_number(phone, country_code)
    base = f"https://wa.me/{number}" if number else "https://wa.me/"
    return f"{base}?text={quote(text)}"


# --- Actions ---------------------------------------------------------------

def create_link(doc_type, obj, company, user):
    d = DOC_TYPES[doc_type]
    return ShareLink.objects.create(
        doc_type=doc_type, doc_id=obj.pk, label=f"{d.title} {d.number(obj)}"[:120], created_by=user,
        expires_at=timezone.now() + timedelta(days=company.share_link_days))


def smtp_ready(company):
    return bool(company.email_host and (company.email_from_address or company.email_username))


def send_email(doc_type, obj, company, user, to, cc, subject, body, request=None):
    if not smtp_ready(company):
        raise SendError(_("Email is not set up. Add your email server in Company settings → Email."))
    pdf, _html = render_pdf(doc_type, obj, company)
    from_addr = company.email_from_address or company.email_username
    sender = f"{company.email_from_name or company.name} <{from_addr}>"
    connection = get_connection(host=company.email_host, port=company.email_port, username=company.email_username,
                                password=decrypt_secret(company.email_password), use_tls=company.email_use_tls,
                                use_ssl=company.email_use_ssl, timeout=20)
    message = EmailMessage(subject=subject, body=body, from_email=sender, to=to, cc=cc,
                           reply_to=[company.email] if company.email else None, connection=connection)
    if pdf is not None:
        message.attach(filename_for(doc_type, obj), pdf, "application/pdf")
    else:
        link = create_link(doc_type, obj, company, user)
        message.body += "\n\n" + _("View the document: %(url)s") % {"url": link_url(link, request)}
    recipients = ", ".join(to + cc)
    try:
        message.send()
    except Exception as exc:  # network / login problems are reported to the user, not crashed on
        SentMessage.objects.create(doc_type=doc_type, doc_id=obj.pk, channel=SentMessage.Channel.EMAIL,
                                   recipient=recipients[:300], subject=subject[:200], ok=False,
                                   error=str(exc)[:300], sent_by=user)
        raise SendError(_("The email could not be sent: %(err)s") % {"err": exc}) from exc
    SentMessage.objects.create(doc_type=doc_type, doc_id=obj.pk, channel=SentMessage.Channel.EMAIL,
                               recipient=recipients[:300], subject=subject[:200], sent_by=user)


def link_url(link, request=None):
    path = f"/s/{link.token}/"
    if request is not None:
        return request.build_absolute_uri(path)
    base = getattr(settings, "PUBLIC_BASE_URL", "").rstrip("/")
    return f"{base}{path}"
