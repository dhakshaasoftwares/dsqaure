from django import template

from apps.sharing.models import SentMessage

register = template.Library()


@register.inclusion_tag("sharing/_sent_log_list.html", takes_context=True)
def sent_log(context, doc_type, doc):
    return {"sent": SentMessage.objects.filter(doc_type=doc_type, doc_id=doc.pk).select_related("sent_by")[:10]}
