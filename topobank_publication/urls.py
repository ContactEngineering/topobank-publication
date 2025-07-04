from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from topobank_publication import views

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(r"publication", views.PublicationViewSet, basename="publication-api")
router.register(
    r"publication-collection",
    views.PublicationCollectionViewSet,
    basename="publication-collection-api",
)

urlpatterns = router.urls

app_name = "topobank_publication"
urlprefix = "go/"
urlpatterns += [
    path("publish/", view=views.publish, name="publish"),
    path(
        "publish-collection/",
        view=views.publish_collection,
        name="publish-collection",
    ),
    path("collection/<str:short_url>/", view=views.go_collection, name="go-collection"),
    path("<str:short_url>/", view=views.go, name="go"),
]
