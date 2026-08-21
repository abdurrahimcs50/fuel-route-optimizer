from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Fuel Route Optimizer Admin"
admin.site.site_title = "Fuel Route Optimizer"
admin.site.index_title = "Administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("routing.urls")),
]
