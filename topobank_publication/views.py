import logging

from django.http import Http404, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import HttpResponse, redirect
from django.urls import reverse
from django.utils.html import json
from rest_framework import mixins, viewsets
from topobank.manager.models import Surface
from topobank.usage_stats.utils import increase_statistics_by_date_and_object
from trackstats.models import Metric, Period

from .models import Publication
from .serializers import PublicationSerializer
from .utils import NewPublicationTooFastException, PublicationException

_log = logging.getLogger(__name__)


def publish(request):
    """
    This view is called when the user clicks "Publish".
    It checks if the provided data is valid and creates the publication.
    """
    data = json.loads(request.body)

    surface: Surface = Surface.objects.get(pk=data["surface"])
    license = data.get("license")
    authors = data.get("authors")

    # TODO: Validation:
    # - max authors
    # - authors json in general...

    # NOTE: Check if the request is malformed
    if license is None or authors is None or surface is None:
        return HttpResponseBadRequest()

    # NOTE: Check if the user has the required permissions to publish:
    if not surface.has_permission(request.user, "full"):
        return HttpResponseForbidden()

    # NOTE: Publish
    try:
        publication = Publication.publish(surface, license, request.user, authors)
        return HttpResponse(content=f"{publication.surface.id}".encode())
    except NewPublicationTooFastException as rate_limit_exception:
        # TODO: content as bytes
        return HttpResponse(
            status=429, content=f"{rate_limit_exception._wait_seconds}".encode()
        )
    except PublicationException as exc:
        msg = f"Publication failed, reason: {exc}"
        _log.error(msg)
        return HttpResponseForbidden()


def go(request, short_url):
    """Visit a published surface by short url."""
    try:
        pub = Publication.objects.get(short_url=short_url)
    except Publication.DoesNotExist:
        raise Http404()

    increase_statistics_by_date_and_object(
        Metric.objects.PUBLICATION_VIEW_COUNT, period=Period.DAY, obj=pub
    )

    if (
        "HTTP_ACCEPT" in request.META
        and "application/json" in request.META["HTTP_ACCEPT"]
    ):
        return redirect(pub.get_api_url())
    else:
        return redirect(
            f"{reverse('ce_ui:surface-detail')}?surface={pub.surface.pk}"
        )  # <- topobank does not know this


class PublicationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = PublicationSerializer

    # FIXME! This view needs pagination

    def get_queryset(self):
        q = Publication.objects.all()
        order_by_version = False
        try:
            original_surface = int(
                self.request.query_params.get("original_surface", default=None)
            )
            q = q.filter(original_surface=original_surface)
            order_by_version = True
        except TypeError:
            pass
        try:
            surface = int(self.request.query_params.get("surface", default=None))
            q = q.filter(surface=surface)
            order_by_version = True
        except TypeError:
            pass
        if order_by_version:
            q = q.order_by("-version")
        return q
