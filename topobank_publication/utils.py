import logging

from topobank.users.anonymous import get_anonymous_user

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
    pass


def set_publication_permissions(surface):
    """Sets all permissions as needed for publication.

    - removes edit, share and delete permission from everyone
    - add read permission for everyone
    """
    # Superusers cannot publish
    if surface.creator.is_superuser:
        raise PublicationException("Superusers cannot publish!")

    # Remove edit, share and delete permission from everyone
    users_with_access = [
        perm.user for perm in surface.permissions.user_permissions.all()
    ]
    for user in users_with_access:
        surface.revoke_permission(user)

    # Add read permission for anonymous user
    surface.grant_permission(get_anonymous_user(), "view")
