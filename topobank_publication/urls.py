from django.urls import path

from rest_framework.routers import DefaultRouter

from topobank_publication import views

router = DefaultRouter()
router.register(
    r"api/publication", views.PublicationViewSet, basename="publication-api"
)

urlpatterns = router.urls

app_name = "topobank_publication"
urlprefix = "publication/"
urlpatterns += [
    path("publish/", view=views.publish, name="test"),
    # FIXME: This url has to be absolute
    path("/go/<str:short_url>/", view=views.go, name="go"),
]
