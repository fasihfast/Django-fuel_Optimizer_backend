"""
Project-level URL routing.

Spring Boot analogy: this is like your top level @RequestMapping router -
it just says "anything under /api/ goes to the routing app's urls.py",
similar to mounting a Router in Express with app.use('/api', router).
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("routing.urls")),
]
