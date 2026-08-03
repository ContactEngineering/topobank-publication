import logging
from typing import NamedTuple

from topobank.authorization import get_anonymous_user

_log = logging.getLogger(__name__)


class PublicationException(Exception):
    """A general exception related to publications."""

    pass


class PublicationsDisabledException(PublicationException):
    """Publications are not allowed due to settings."""

    pass


class AlreadyPublishedException(PublicationException):
    """A surface has already been published."""

    pass


EMPTY_DATASET_MESSAGE = (
    "A dataset must contain at least one measurement before it can be published."
)


class EmptyDatasetException(PublicationException):
    """A surface without any measurements cannot be published."""

    pass


# Why a measurement is not ready for publication.
REASON_NOT_PROCESSED = "not-processed"
REASON_INCOMPLETE_METADATA = "incomplete-metadata"

# The fields required by `Topography.is_metadata_complete`, with the labels shown
# to the user. Kept deliberately in sync with that property rather than calling
# it, so that readiness can be evaluated in a single query.
#
# Note that `height_scale` currently has a non-null default and therefore never
# actually blocks; it is listed to stay faithful to `is_metadata_complete`.
REQUIRED_METADATA_FIELDS = (
    ("size_x", "physical size"),
    ("unit", "unit"),
    ("height_scale", "height scale"),
)


def missing_metadata(topography):
    """Labels of the metadata fields `topography` is still missing."""
    return tuple(
        label
        for field, label in REQUIRED_METADATA_FIELDS
        if getattr(topography, field) is None
    )


class UnreadyMeasurement(NamedTuple):
    """A measurement that blocks publication, together with the reason why."""

    topography: object
    reason: str
    missing_metadata: tuple

    def describe(self):
        """Short parenthetical describing what is wrong with this measurement."""
        if self.reason == REASON_INCOMPLETE_METADATA:
            return f"missing {', '.join(self.missing_metadata)}"
        return self.topography.get_task_state_display()


def describe_unready_measurements(measurements):
    """Human-readable reason why `measurements` block publication."""
    details = ", ".join(
        f"'{measurement.topography.name}' ({measurement.describe()})"
        for measurement in measurements
    )
    return (
        "All measurements must have been processed successfully and have complete "
        f"metadata before a dataset can be published. Not ready: {details}."
    )


class MeasurementsNotReadyException(PublicationException):
    """Not all measurements of a surface are ready for publication."""

    def __init__(self, measurements):
        self._measurements = list(measurements)

    @property
    def measurements(self):
        return self._measurements

    def __str__(self):
        return describe_unready_measurements(self._measurements)


class NewPublicationTooFastException(PublicationException):
    """A new publication has been issued to fast after the former one."""

    def __init__(self, latest_publication, wait_seconds):
        self._latest_pub = latest_publication
        self._wait_seconds = wait_seconds

    def __str__(self):
        s = f"Latest publication for this surface is from {self._latest_pub.datetime}. "
        s += f"Please wait {self._wait_seconds} more seconds before publishing again."
        return s


class UnknownCitationFormat(Exception):
    """Exception thrown when an unknown citation format should be handled."""

    def __init__(self, flavor):
        self._flavor = flavor

    def __str__(self):
        return f"Unknown citation format flavor '{self._flavor}'."


class DOICreationException(Exception):
    """Raised when DOI creation at DataCite fails.

    Attributes
    ----------
    remote_created : bool
        Whether the DOI may already have been created remotely at DataCite when
        the failure occurred. If ``False`` the remote creation definitely did not
        happen (e.g. a pre-flight schema validation error, or a failure on the
        very first draft_doi call), so a caller can safely roll back. If ``True``
        the remote state is ambiguous (a registered/findable DOI may exist and
        cannot be deleted), so the caller must NOT strand it by rolling back.
    """

    def __init__(self, *args, remote_created: bool = False):
        super().__init__(*args)
        self.remote_created = remote_created


def unready_measurements(surface):
    """Return the measurements of `surface` that block its publication.

    Publication takes an immutable, permanently read-only copy of the dataset
    (see `set_publication_permissions`), so anything that would still need
    fixing must be caught beforehand: on the copy it could never be corrected
    or removed, and the dataset would stay broken under a citable DOI.

    A measurement is ready only if both of the following hold:

    - Its task state is SUCCESS. FAILURE blocks for the reason above; the
      in-flight states and NOTRUN block because their outcome is not known yet
      and may well turn out to be a failure.
    - Its metadata is complete in the sense of
      `Topography.is_metadata_complete`. SUCCESS alone is *not* sufficient:
      unless the instance sets `TOPOBANK_REJECT_INCOMPLETE_METADATA`,
      `refresh_cache` skips thumbnail, deepzoom, squeezed data file and
      bandwidth generation for a measurement with missing physical size or
      unit, yet still completes and is recorded as SUCCESS. Such a measurement
      cannot be plotted or analysed, and it is exactly the case where the user
      is expected to supply the missing values by hand -- which the read-only
      copy makes impossible.

    Note that `surface.topography_set` uses the default manager, so
    soft-deleted measurements are correctly ignored.

    Returns
    -------
    list of UnreadyMeasurement
        Blocking measurements, ordered by name. Empty if the surface is ready.
    """
    from topobank.manager.models import Topography

    # A single `exclude` with several conditions excludes the rows where *all*
    # of them hold, i.e. it keeps exactly the measurements that are not ready.
    blocking = surface.topography_set.exclude(
        task_state=Topography.SUCCESS,
        **{f"{field}__isnull": False for field, _ in REQUIRED_METADATA_FIELDS},
    ).order_by("name")

    return [
        UnreadyMeasurement(
            topography=topography,
            reason=(
                REASON_NOT_PROCESSED
                if topography.task_state != Topography.SUCCESS
                else REASON_INCOMPLETE_METADATA
            ),
            missing_metadata=missing_metadata(topography),
        )
        for topography in blocking
    ]


def set_publication_permissions(surface):
    """Sets all permissions as needed for publication.

    - removes edit, share and delete permission from everyone
    - add read permission for everyone
    """
    # Superusers cannot publish
    if surface.created_by.is_superuser:
        raise PublicationException("Superusers cannot publish!")

    # Remove edit, share and delete permission from everyone
    users_with_access = [
        perm.user for perm in surface.permissions.user_permissions.all()
    ]
    for user in users_with_access:
        surface.revoke_permission(user)

    # Add read permission for anonymous user
    surface.grant_permission(get_anonymous_user(), "view")
