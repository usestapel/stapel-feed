from django.urls import include, path

urlpatterns = [
    path("feed/api/", include("stapel_feed.urls")),
]
