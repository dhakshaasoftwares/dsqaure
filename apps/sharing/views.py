from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.validators import validate_email
from django.db.models import F
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.core.models import CompanySettings

from .models import SentMessage, ShareLink
from .registry import DOC_TYPES
from .services import (SendError, create_link, fill, filename_for, link_url, placeholders, render_pdf, send_email,
                       smtp_ready, whatsapp_url)


def _emails(value):
    result = []
    for part in (value or "").replace(";", ",").split(","):
        part = part.strip()
        if part:
            validate_email(part)
            result.append(part)
    return result


class EmailForm(forms.Form):
    to = forms.CharField(label=gettext_lazy("To"), help_text=gettext_lazy("Separate several addresses with commas"))
    cc = forms.CharField(label=gettext_lazy("Copy to (CC)"), required=False)
    subject = forms.CharField(label=gettext_lazy("Subject"), max_length=200)
    body = forms.CharField(label=gettext_lazy("Message"), widget=forms.Textarea(attrs={"rows": 6}))

    def clean_to(self):
        try:
            emails = _emails(self.cleaned_data["to"])
        except forms.ValidationError:
            raise forms.ValidationError(_("Enter valid email addresses."))
        if not emails:
            raise forms.ValidationError(_("Enter at least one email address."))
        return emails

    def clean_cc(self):
        try:
            return _emails(self.cleaned_data.get("cc"))
        except forms.ValidationError:
            raise forms.ValidationError(_("Enter valid email addresses."))


class WhatsAppForm(forms.Form):
    phone = forms.CharField(label=gettext_lazy("WhatsApp number"), max_length=30, required=False,
                            help_text=gettext_lazy("Leave blank to choose the contact inside WhatsApp"))
    text = forms.CharField(label=gettext_lazy("Message"), widget=forms.Textarea(attrs={"rows": 4}))


def get_document(request, doc_type, pk):
    d = DOC_TYPES.get(doc_type)
    if d is None:
        raise Http404
    if not request.company.module_enabled(d.module):
        raise Http404
    if not (request.user.has_perm(d.perm) and request.user.has_perm("sharing.add_sentmessage")):
        raise PermissionDenied
    return d, get_object_or_404(d.model, pk=pk)


@login_required
def share(request, doc_type, pk):
    d, obj = get_document(request, doc_type, pk)
    company = request.company
    name, email, phone = d.recipient(obj)
    values = placeholders(doc_type, obj, company, link=_("(link is added when you press Send)"))
    email_form = EmailForm(prefix="email", initial={
        "to": email, "subject": fill(company.email_subject_template, values),
        "body": fill(company.email_body_template, placeholders(doc_type, obj, company))})
    wa_form = WhatsAppForm(prefix="wa", initial={"phone": phone, "text": fill(company.whatsapp_template, values)})

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "email":
            email_form = EmailForm(request.POST, prefix="email")
            if email_form.is_valid():
                data = email_form.cleaned_data
                try:
                    send_email(doc_type, obj, company, request.user, data["to"], data["cc"], data["subject"],
                               data["body"], request=request)
                    messages.success(request, _("Email sent to %(to)s.") % {"to": ", ".join(data["to"])})
                    return redirect(d.detail_url(obj))
                except SendError as exc:
                    messages.error(request, str(exc))
        elif action == "whatsapp":
            wa_form = WhatsAppForm(request.POST, prefix="wa")
            if wa_form.is_valid():
                link = create_link(doc_type, obj, company, request.user)
                text = wa_form.cleaned_data["text"]
                url = link_url(link, request)
                text = text.replace(_("(link is added when you press Send)"), url)
                if url not in text:
                    text = f"{text}\n{url}"
                SentMessage.objects.create(doc_type=doc_type, doc_id=obj.pk, channel=SentMessage.Channel.WHATSAPP,
                                           recipient=wa_form.cleaned_data["phone"] or "-", sent_by=request.user)
                return redirect(whatsapp_url(wa_form.cleaned_data["phone"], text, company.whatsapp_country_code))
        elif action == "link":
            link = create_link(doc_type, obj, company, request.user)
            SentMessage.objects.create(doc_type=doc_type, doc_id=obj.pk, channel=SentMessage.Channel.LINK,
                                       recipient=link_url(link, request), sent_by=request.user)
            messages.success(request, _("Link created. Copy it from the list below."))
            return redirect(request.path)

    return render(request, "sharing/share.html", {
        "d": d, "obj": obj, "doc_type": doc_type, "number": d.number(obj), "recipient_name": name,
        "email_form": email_form, "wa_form": wa_form, "smtp_ready": smtp_ready(company),
        "links": ShareLink.objects.filter(doc_type=doc_type, doc_id=obj.pk)[:10],
        "sent": SentMessage.objects.filter(doc_type=doc_type, doc_id=obj.pk).select_related("sent_by")[:20],
        "back_url": d.detail_url(obj), "filename": filename_for(doc_type, obj),
        "pdf_url": request.build_absolute_uri(f"{request.path}pdf/"),
    })


@login_required
def share_pdf(request, doc_type, pk):
    """The PDF itself, fetched by the phone's share sheet."""
    d, obj = get_document(request, doc_type, pk)
    pdf, html = render_pdf(doc_type, obj, request.company)
    if pdf is None:
        return HttpResponse(html)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename_for(doc_type, obj)}"'
    return response


@require_POST
@login_required
def revoke(request, link_pk):
    link = get_object_or_404(ShareLink, pk=link_pk)
    get_document(request, link.doc_type, link.doc_id)
    link.revoked = True
    link.save(update_fields=["revoked"])
    messages.success(request, _("Link stopped. It no longer opens."))
    return redirect("sharing:share", doc_type=link.doc_type, pk=link.doc_id)


def public(request, token):
    """What the client / supplier sees when they open the link: just the PDF, no login."""
    link = ShareLink.objects.filter(token=token).first()
    if link is None or not link.is_active:
        return render(request, "sharing/link_expired.html", status=410)
    d = DOC_TYPES.get(link.doc_type)
    obj = d.model.objects.filter(pk=link.doc_id).first() if d else None
    if obj is None:
        return render(request, "sharing/link_expired.html", status=410)
    ShareLink.objects.filter(pk=link.pk).update(view_count=F("view_count") + 1, last_viewed_at=timezone.now())
    pdf, html = render_pdf(link.doc_type, obj, CompanySettings.load())
    if pdf is None:
        return HttpResponse(html)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename_for(link.doc_type, obj)}"'
    response["X-Robots-Tag"] = "noindex"
    response["Cache-Control"] = "private, no-store"
    return response
