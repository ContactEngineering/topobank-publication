"""
Version information about a published dataset, for the dataset list.

The list shows only the latest version of a dataset (see
`topobank_rest_api.manager.filters.filter_to_latest_version`), so the row has to
say which version that is and that there are others — otherwise collapsing the
versions hides them without a trace.
"""

from rest_framework import serializers

from .models import Publication


def version_of(surface):
    """Which version of its dataset a surface is.

    Parameters
    ----------
    surface : topobank.manager.models.Surface

    Returns
    -------
    int or None
        The version number, or None for a dataset that is not published.
    """
    publication = getattr(surface, "publication", None)
    return None if publication is None else publication.version


def nb_versions_of(surface):
    """How many published versions the dataset of a surface has.

    Counted over the publications that share the same original, which is the
    grouping the dataset list collapses by. A publication that records no
    original cannot be grouped and counts as one on its own.

    Parameters
    ----------
    surface : topobank.manager.models.Surface

    Returns
    -------
    int or None
        The number of published versions, or None for a dataset that is not
        published.
    """
    publication = getattr(surface, "publication", None)
    if publication is None:
        return None
    if publication.original_surface_id is None:
        return 1
    return Publication.objects.filter(
        original_surface_id=publication.original_surface_id
    ).count()


def patch_surface_serializer(serializer_class):
    """Add `version` and `nb_versions` to a surface serializer.

    Follows the same monkey-patching route as the `publication` field: the
    serializer lives in `topobank-rest-api`, which does not know about
    publications, and this plugin is optional, so the fields are attached when it
    starts up rather than declared there.
    """
    fields = {
        "version": serializers.SerializerMethodField(),
        "nb_versions": serializers.SerializerMethodField(),
    }
    serializer_class.Meta.fields = list(serializer_class.Meta.fields) + list(fields)
    for name, field in fields.items():
        setattr(serializer_class, name, field)
        serializer_class.__dict__["_declared_fields"][name] = field
    # A `SerializerMethodField` resolves through `get_<field name>`.
    serializer_class.get_version = lambda self, obj: version_of(obj)
    serializer_class.get_nb_versions = lambda self, obj: nb_versions_of(obj)
