from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from topobank_publication import views, oaipmh_views, sitemap_views

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(r"publication", views.PublicationViewSet, basename="publication-api")
router.register(
    r"publication-collection",
    views.PublicationCollectionViewSet,
    basename="publication-collection-api",
)

urlpatterns = router.urls

app_name = "publication"
urlprefix = "go/"
urlpatterns += [
    path("publish/", view=views.publish, name="publish"),
    path(
        "publishable/<int:surface_id>/",
        view=views.publication_readiness,
        name="publication-readiness",
    ),
    path(
        "publish-collection/",
        view=views.publish_collection,
        name="publish-collection",
    ),
    path("collection/<str:short_url>/", view=views.go_collection, name="go-collection"),
    path("oai/", view=oaipmh_views.oai_pmh_view, name="oai-pmh"),
    # GET
    # * Sitemap of all published datasets, so that crawlers can discover them
    #   without executing the JavaScript of the app. Declared before the
    #   catch-all `go` route below.
    path("sitemap.xml", view=sitemap_views.sitemap_view, name="sitemap"),
    # GET
    # * Redirect to the archived container of a published dataset. Must be
    #   declared before the catch-all `go` route below.
    path(
        "<str:short_url>/download/",
        view=views.download_container,
        name="download-container",
    ),
    # GET
    # * Serve the schema.org description of a published dataset. Also available
    #   by content negotiation on the `go` route below, but a URL of its own is
    #   what typed links can point at.
    path(
        "<str:short_url>/metadata/",
        view=views.metadata,
        name="metadata",
    ),
    path("<str:short_url>/", view=views.go, name="go"),
]
