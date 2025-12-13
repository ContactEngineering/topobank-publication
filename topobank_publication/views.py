import logging

import pydantic
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import HttpResponse, get_object_or_404, redirect
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from topobank.manager.models import Surface
from topobank.usage_stats.utils import increase_statistics_by_date_and_object
from trackstats.models import Metric, Period

from .models import Publication, PublicationCollection
from .serializers import PublicationCollectionSerializer, PublicationSerializer
from .utils import (AlreadyPublishedException, NewPublicationTooFastException,
                    PublicationException)

_log = logging.getLogger(__name__)


@api_view(["POST"])
@login_required
def publish_collection(request):
    pks = request.data.get("publication")
    title = request.data.get("title")
    description = request.data.get("description", "")
    if pks is None:
        return HttpResponseBadRequest(reason="Missing publication id's")
    if len(pks) < 2:
        return HttpResponseBadRequest(reason="Not 2 or more id's provided")
    if title is None:
        return HttpResponseBadRequest(reason="Missing title")
    publications = [get_object_or_404(Publication, pk=pk) for pk in pks]
    # TODO: Check for duplications
    try:
        collection = PublicationCollection.publish(
            publications, title, description, request.user
        )
    except AlreadyPublishedException:
        msg = "This Collection has already been published."
        _log.error(msg)
        return HttpResponseBadRequest(reason=msg)
    except PublicationException as exc:
        msg = f"Publication failed, reason: {exc}"
        _log.error(msg)
        return HttpResponseBadRequest(reason=msg)

    # TODO: Handle expections that occur during publish
    return Response({"collection_id": collection.id})


@api_view(["POST"])
def publish(request):
    """
    This view is called when the user clicks "Publish".
    It checks if the provided data is valid and creates the publication.
    """
    #
    # Get dataset
    #
    pk = request.data.get("surface")
    if pk is None:
        return HttpResponseBadRequest(reason="Missing dataset id")
    surface = get_object_or_404(Surface, pk=pk)

    #
    # Get license
    #
    license = request.data.get("license")

    #
    # Get authors
    #
    authors = request.data.get("authors")

    #
    # Check if the request is malformed
    #
    if license is None:
        return HttpResponseBadRequest(reason="Missing license")
    if authors is None:
        return HttpResponseBadRequest(reason="Missing authors")

    #
    # Check if the user has the required permissions to publish
    #
    if not surface.has_permission(request.user, "full"):
        return HttpResponseForbidden(
            reason="User does not have permission to publish this dataset"
        )

    #
    # Publish
    #
    try:
        publication = Publication.publish(surface, license, request.user, authors)
        return Response({"dataset_id": publication.surface.id})
    except NewPublicationTooFastException as rate_limit_exception:
        return HttpResponse(
            status=429, content=str.encode(f"{rate_limit_exception._wait_seconds}")
        )
    except PublicationException as exc:
        msg = f"Publication failed, reason: {exc}"
        _log.error(msg)
        return HttpResponseBadRequest(reason=msg)
    except pydantic.ValidationError as exc:
        msg = f"Failed to validate authors: {exc}"
        _log.error(msg)
        return HttpResponseBadRequest(reason=msg)


def go_collection(request, short_url):
    """Visit a publication collection by short url."""
    try:
        collection: PublicationCollection = PublicationCollection.objects.get(
            short_url=short_url
        )
    except PublicationCollection.DoesNotExist:
        raise Http404()
    return redirect(f"/ui/dataset-collection/{collection.id}")


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
            f"/ui/dataset-detail/{pub.surface.pk}/"
        )  # <- topobank does not know this


class PublicationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = PublicationSerializer
    pagination_class = LimitOffsetPagination

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


class PublicationCollectionViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = PublicationCollectionSerializer
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        return PublicationCollection.objects.all()
