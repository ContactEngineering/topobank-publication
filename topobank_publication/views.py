import logging
import os.path

import pydantic
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import Http404, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import HttpResponse, get_object_or_404, redirect
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from topobank.manager.models import Surface

from .models import Publication, PublicationCollection
from .serializers import PublicationCollectionSerializer, PublicationSerializer
from .utils import (EMPTY_DATASET_MESSAGE, AlreadyPublishedException,
                    NewPublicationTooFastException, PublicationException,
                    describe_unready_measurements, unready_measurements)

_log = logging.getLogger(__name__)


@api_view(["POST"])
@login_required
def publish_collection(request):
    pks = request.data.get("publication")
    title = request.data.get("title")
    description = request.data.get("description", "")
    if pks is None:
        return HttpResponseBadRequest(reason="Missing publication id's")
    if title is None:
        return HttpResponseBadRequest(reason="Missing title")

    #
    # Deduplicate the provided ids (preserving order) and only then check that
    # at least two *distinct* publications were requested.
    #
    deduped_pks = list(dict.fromkeys(pks))
    if len(deduped_pks) < 2:
        return HttpResponseBadRequest(reason="Not 2 or more id's provided")

    publications = [get_object_or_404(Publication, pk=pk) for pk in deduped_pks]

    #
    # A DOI collection may only be built from publications the requesting user
    # actually owns (is the publisher of). Otherwise any user could mint a DOI
    # collection referencing arbitrary other users' publications.
    #
    for pub in publications:
        is_publisher = pub.publisher_id == request.user.id
        if not (is_publisher or request.user.is_staff):
            return HttpResponseForbidden(
                reason=(
                    f"You do not have permission to include publication {pub.pk} "
                    f"in a collection."
                )
            )

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


@api_view(["GET"])
def publication_readiness(request, surface_id):
    """
    Report whether a dataset can currently be published.

    The publish wizard queries this up front so that a dataset which would be
    rejected by `Publication.publish` is flagged before the user fills in
    authors and a license, rather than at the final "Publish" step.

    This reports the conditions that are stable enough to be worth showing
    early. Two conditions that `publish` also enforces are deliberately not
    reported: the rate limit, because it expires on its own and is already
    reported as a 429 by `publish`; and "already published", because
    publication revokes every user permission on the copy, so an already
    published surface is rejected by the permission check below anyway.
    """
    surface = get_object_or_404(Surface, pk=surface_id)

    if not surface.has_permission(request.user, "full"):
        return HttpResponseForbidden(
            reason="User does not have permission to publish this dataset"
        )

    blockers = []

    if not settings.PUBLICATION_ENABLED:
        blockers.append(
            {
                "code": "publications-disabled",
                "message": "Publishing is currently disabled on this instance.",
            }
        )

    if not surface.topography_set.exists():
        blockers.append(
            {"code": "no-measurements", "message": EMPTY_DATASET_MESSAGE}
        )

    not_ready = unready_measurements(surface)
    if not_ready:
        blockers.append(
            {
                "code": "measurements-not-ready",
                "message": describe_unready_measurements(not_ready),
            }
        )

    return Response(
        {
            "publishable": len(blockers) == 0,
            "blockers": blockers,
            "unready_measurements": [
                {
                    "id": measurement.topography.id,
                    "name": measurement.topography.name,
                    "reason": measurement.reason,
                    "detail": measurement.describe(),
                    "task_state": measurement.topography.task_state,
                    "task_state_display": (
                        measurement.topography.get_task_state_display()
                    ),
                    "missing_metadata": list(measurement.missing_metadata),
                }
                for measurement in not_ready
            ],
        }
    )


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
    except IntegrityError as exc:
        # A concurrent publish of the same surface can race to the
        # unique_together ("original_surface", "version") constraint. Report a
        # 409 Conflict rather than letting it surface as an HTTP 500.
        msg = (
            "Publication failed due to a concurrent publication of the same "
            "dataset. Please try again."
        )
        _log.error("%s Reason: %s", msg, exc)
        return HttpResponse(status=status.HTTP_409_CONFLICT, content=str.encode(msg))
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


@api_view(["GET"])
def download_container(request, short_url):
    """Download the archived container of a published dataset."""
    pub = get_object_or_404(Publication, short_url=short_url)

    # Published datasets are public, but go through the permission check anyway
    # so that this route cannot outlive a change to that rule
    if not pub.surface.has_permission(request.user, "view"):
        return HttpResponseForbidden()

    if not pub.has_container:
        pub.renew_container()

    if getattr(settings, "USE_S3_STORAGE", False):
        return redirect(pub.container.url)

    response = HttpResponse(
        pub.container.read(), content_type="application/x-zip-compressed"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{os.path.basename(pub.container_storage_path)}"'
    )
    return response


def go(request, short_url):
    """Visit a published surface by short url."""
    try:
        pub = Publication.objects.get(short_url=short_url)
    except Publication.DoesNotExist:
        raise Http404()

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
        except (TypeError, ValueError):
            # TypeError: param absent (int(None)); ValueError: non-numeric value
            # such as ?original_surface=abc. Either way, skip this filter.
            pass
        try:
            surface = int(self.request.query_params.get("surface", default=None))
            q = q.filter(surface=surface)
            order_by_version = True
        except (TypeError, ValueError):
            # TypeError: param absent (int(None)); ValueError: non-numeric value
            # such as ?surface=abc. Either way, skip this filter.
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
