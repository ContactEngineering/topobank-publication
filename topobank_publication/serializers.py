from rest_framework import serializers
from rest_framework.reverse import reverse

from .models import CITATION_FORMAT_FLAVORS, Publication, PublicationCollection


class PublicPublisherSerializer(serializers.Serializer):
    """Minimal, public-safe representation of a publisher.

    The publication API is readable by anonymous users, so the publisher must
    only expose non-sensitive fields. This deliberately serializes just the
    public name/username and ORCID information and must NOT include email,
    is_staff, date_joined or any other private user field (as the full
    UserSerializer would).
    """

    name = serializers.CharField(read_only=True)
    username = serializers.CharField(read_only=True)
    orcid_id = serializers.SerializerMethodField()
    orcid_uri = serializers.SerializerMethodField()

    def get_orcid_id(self, obj) -> str:
        return getattr(obj, "orcid_id", None)

    def get_orcid_uri(self, obj) -> str:
        orcid_id = getattr(obj, "orcid_id", None)
        return f"https://orcid.org/{orcid_id}" if orcid_id else None


class PublicationSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Publication
        fields = [
            "url",
            "id",
            "short_url",
            "surface",
            "original_surface",
            "publisher",
            "publisher_orcid_id",
            "version",
            "datetime",
            "license",
            "authors_json",
            "datacite_json",
            "doi_name",
            "doi_state",
            "citation",
            "has_access_to_original_surface",
            "download_url",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="publication:publication-api-detail", read_only=True
    )
    surface = serializers.HyperlinkedRelatedField(
        view_name="manager:surface-api-detail", read_only=True
    )
    original_surface = serializers.HyperlinkedRelatedField(
        view_name="manager:surface-api-detail", read_only=True
    )
    publisher = PublicPublisherSerializer(read_only=True)
    citation = serializers.SerializerMethodField()
    has_access_to_original_surface = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    def get_citation(self, obj):
        d = {}
        for flavor in CITATION_FORMAT_FLAVORS:
            d[flavor] = obj.get_citation(flavor)
        return d

    def get_has_access_to_original_surface(self, obj):
        if obj.original_surface:
            return obj.original_surface.has_permission(
                self.context["request"].user, "view"
            )
        return False

    def get_download_url(self, obj):
        return reverse(
            "manager:surface-download",
            kwargs={"surface_ids": str(obj.surface.id)},
            request=self.context["request"],
        )


class PublicationCollectionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = PublicationCollection
        fields = [
            "id",
            "url",
            "doi_name",
            "title",
            "description",
            "short_url",
            "publisher",
            "publications",
        ]

    url = serializers.HyperlinkedIdentityField(
        view_name="publication:publication-collection-api-detail", read_only=True
    )
    publisher = PublicPublisherSerializer(read_only=True)
    publications = serializers.HyperlinkedRelatedField(
        view_name="publication:publication-api-detail", many=True, read_only=True
    )
