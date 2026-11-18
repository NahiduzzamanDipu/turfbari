from django.contrib import admin

from .models import Area, District, Division

admin.site.register([Division, District, Area])
