from .models import CompanySettings


def company(request):
    return {"company": getattr(request, "company", None) or CompanySettings.load()}
