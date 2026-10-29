from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .keys import ALL_MODULES, LicenceError
from .models import Installation
from .service import active_user_count, check_key, get_status


class LicenceKeyForm(forms.Form):
    key = forms.CharField(label=gettext_lazy("Licence key"), widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, installation=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.installation = installation

    def clean_key(self):
        key = "".join(self.cleaned_data["key"].split())
        try:
            self.licence = check_key(key, self.installation)
        except LicenceError as exc:
            raise forms.ValidationError(str(exc))
        return key


@login_required
def licence_page(request):
    if not (request.user.is_superuser or request.user.has_perm("core.change_companysettings")):
        raise PermissionDenied
    installation = Installation.load()
    form = LicenceKeyForm(request.POST or None, installation=installation)
    if request.method == "POST" and form.is_valid():
        installation.licence_key = form.cleaned_data["key"]
        installation.activated_at = timezone.now()
        installation.save()
        messages.success(request, _("Licence activated for %(name)s until %(date)s.") % {
            "name": form.licence.licensee, "date": form.licence.expires.strftime("%d %b %Y")})
        return redirect("licensing:licence")
    status = get_status(installation)
    return render(request, "licensing/licence.html", {
        "installation": installation, "status": status, "form": form, "users_active": active_user_count(),
        "module_names": ALL_MODULES,
    })
