from django import forms
from django.utils.translation import ugettext_lazy as _


class MoonScanForm(forms.Form):
    scan = forms.CharField(widget=forms.Textarea)
