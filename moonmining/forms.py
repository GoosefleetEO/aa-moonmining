from django import forms


class MoonScanForm(forms.Form):
    scan = forms.CharField(widget=forms.Textarea)
