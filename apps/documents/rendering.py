"""
Turns agreement text with {placeholders} into safe HTML.

Templates are written by client staff, so they are never run through the
Django template engine – only the fixed placeholders below are replaced,
and everything is HTML-escaped.
"""

import re

from django.utils.dateformat import format as date_format
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core.numbers import format_money

def plain_number(value):
    """10.00 → '10', 12.50 → '12.5' (never scientific notation like 1E+1)."""
    return format(value.normalize(), "f")


PLACEHOLDERS = [
    ("agreement_number", gettext_lazy("Agreement number")),
    ("agreement_date", gettext_lazy("Agreement date")),
    ("company_name", gettext_lazy("Your company name")),
    ("company_address", gettext_lazy("Your company address")),
    ("company_phone", gettext_lazy("Your company phone")),
    ("signatory_name", gettext_lazy("Authorised signatory")),
    ("client_name", gettext_lazy("Client name")),
    ("client_address", gettext_lazy("Client address")),
    ("client_phone", gettext_lazy("Client phone")),
    ("project_name", gettext_lazy("Project name")),
    ("site_address", gettext_lazy("Site address")),
    ("currency", gettext_lazy("Currency symbol")),
    ("contract_value", gettext_lazy("Contract value")),
    ("start_date", gettext_lazy("Start date")),
    ("completion_date", gettext_lazy("Completion date")),
    ("payment_schedule", gettext_lazy("Payment schedule table")),
]


def _date(value):
    return date_format(value, "d M Y") if value else "________"


def agreement_values(agreement, company):
    client = agreement.client
    project = agreement.project
    return {
        "agreement_number": agreement.number,
        "agreement_date": _date(agreement.date),
        "company_name": company.name,
        "company_address": company.address.replace("\n", ", "),
        "company_phone": company.phone,
        "signatory_name": company.signatory_name,
        "client_name": client.name,
        "client_address": client.address.replace("\n", ", "),
        "client_phone": client.phone,
        "project_name": project.name if project else agreement.title,
        "site_address": (agreement.site_address or (project.address if project else "")).replace("\n", ", "),
        "currency": company.currency_symbol,
        "contract_value": format_money(agreement.contract_value, style=company.number_grouping),
        "start_date": _date(agreement.start_date),
        "completion_date": _date(agreement.completion_date),
    }


def payment_table(agreement, company):
    rows = "".join(
        f"<tr><td>{i}</td><td>{escape(m.description)}</td><td class='num'>{plain_number(m.percent)}%</td>"
        f"<td class='num'>{escape(company.currency_symbol)}{format_money(m.amount, style=company.number_grouping)}</td></tr>"
        for i, m in enumerate(agreement.milestones.all(), start=1)
    )
    if not rows:
        return "<p>________</p>"
    return ("<table class='schedule'><thead><tr><th>#</th><th>" + escape(_("Stage / milestone")) + "</th><th>%</th><th>"
            + escape(_("Amount")) + "</th></tr></thead><tbody>" + rows + "</tbody></table>")


def render_body(text, values, payment_html=""):
    """
    Escape the text, replace placeholders, and format it: blank lines separate
    paragraphs, lines starting with '# ' / '## ' become headings, and
    {payment_schedule} becomes the milestone table.
    """
    marker = "@@PAYMENT_SCHEDULE@@"

    def fill(line):
        line = escape(line.replace("{payment_schedule}", marker))
        return re.sub(r"\{(\w+)\}", lambda m: escape(values.get(m.group(1), m.group(0))), line)

    html = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = [l for l in block.strip().split("\n")]
        paragraph = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## ") or stripped.startswith("# "):
                if paragraph:
                    html.append("<p>" + "<br>".join(paragraph) + "</p>")
                    paragraph = []
                tag = "h3" if stripped.startswith("## ") else "h2"
                html.append(f"<{tag}>{fill(stripped.lstrip('#').strip())}</{tag}>")
            elif stripped:
                paragraph.append(fill(line))
        if paragraph:
            html.append("<p>" + "<br>".join(paragraph) + "</p>")
    out = "\n".join(html)
    out = out.replace(f"<p>{marker}</p>", payment_html).replace(marker, payment_html)
    return mark_safe(out)


def render_agreement(agreement, company):
    return render_body(agreement.body, agreement_values(agreement, company), payment_table(agreement, company))
