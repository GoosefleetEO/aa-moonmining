from django.shortcuts import render
from django.contrib.auth.decorators import login_required
import os
from .models import *

SWAGGER_SPEC_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'swagger.json')


# Create your views here.
@login_required
def moon_index(request):
    return render(request, 'moonstuff/moon_index.html')
