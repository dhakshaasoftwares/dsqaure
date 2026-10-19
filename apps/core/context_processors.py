from .models import CompanySettings


def company(request):
    return {"company": CompanySettings.load()}
