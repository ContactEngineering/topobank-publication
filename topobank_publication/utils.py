import logging

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


def describe_unready_measurements(measurements):
    """Human-readable reason why `measurements` block publication."""
    details = ", ".join(
        f"'{topography.name}' ({topography.get_task_state_display()})"
        for topography in measurements
    )
    return (
        "All measurements must have been processed successfully before a "
        f"dataset can be published. Not ready: {details}."
    )


class MeasurementsNotReadyException(PublicationException):
    """Not all measurements of a surface have been successfully processed."""

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

    Publication requires every measurement to be in state SUCCESS. Only that
    state guarantees the datafile could actually be read and the cached
    metadata plus the squeezed data file exist.

    Every other state blocks:

    - FAILURE, because publication takes an immutable, permanently read-only
      copy (see `set_publication_permissions`). A measurement that fails to
      inspect again on the copy could then never be fixed or removed, and the
      dataset would keep a broken measurement under a citable DOI.
    - The in-flight states and NOTRUN, because their outcome is not known yet
      and may well turn out to be a failure.

    Returns
    -------
    list of Topography
        Blocking measurements, ordered by name. Empty if the surface is ready.
    """
    from topobank.manager.models import Topography

    return list(
        surface.topography_set.exclude(task_state=Topography.SUCCESS).order_by("name")
    )


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
