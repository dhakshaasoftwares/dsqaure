"""
HTML → PDF using WeasyPrint (handles Tamil and other scripts correctly when
Noto fonts are installed). If WeasyPrint's system libraries are missing, the
same page is returned as printable HTML so the user can "Save as PDF".
"""

from django.http import HttpResponse
from django.template.loader import render_to_string

try:
    from weasyprint import HTML
except (ImportError, OSError):  # pragma: no cover - depends on system libraries
    HTML = None


def pdf_response(request, template_name, context, filename, inline=True):
    html = render_to_string(template_name, {**context, "pdf": HTML is not None}, request=request)
    if HTML is None or request.GET.get("format") == "html":
        return HttpResponse(html)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    disposition = "inline" if inline else "attachment"
    safe_name = filename.replace("/", "-").replace('"', "")
    response["Content-Disposition"] = f'{disposition}; filename="{safe_name}.pdf"'
    return response
