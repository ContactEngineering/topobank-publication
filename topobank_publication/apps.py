from rest_framework import serializers
from django.apps import AppConfig


class TopobankPublicationAppConfig(AppConfig):
    name = "topobank_publication"
    label = "publication"
    verbose_name = "Publication"

    def ready(self):
        from topobank_rest_api.manager.v1.serializers import SurfaceSerializer

        # Monkey patch the new field into the serializer
        publication_field = serializers.HyperlinkedRelatedField(
            view_name="publication:publication-api-detail", read_only=True
        )
        SurfaceSerializer.Meta.fields = list(SurfaceSerializer.Meta.fields) + ["publication"]
        SurfaceSerializer.publication = publication_field
        SurfaceSerializer.__dict__["_declared_fields"]["publication"] = (
            publication_field
        )

        # The dataset list shows only the latest version of a dataset, so a row
        # has to be able to say which version it is and that there are others.
        from .version_info import patch_surface_serializer

        patch_surface_serializer(SurfaceSerializer)

        # v2 renders the dataset list straight from the list response, so the
        # publication is embedded as a compact summary rather than a hyperlink
        # that every row would have to fetch separately.
        from topobank_rest_api.manager.v2.serializers import SurfaceV2Serializer

        from .serializers import PublicationSummarySerializer

        publication_summary_field = PublicationSummarySerializer(read_only=True)
        SurfaceV2Serializer.Meta.fields = list(SurfaceV2Serializer.Meta.fields) + [
            "publication"
        ]
        SurfaceV2Serializer.publication = publication_summary_field
        SurfaceV2Serializer.__dict__["_declared_fields"]["publication"] = (
            publication_summary_field
        )

        patch_surface_serializer(SurfaceV2Serializer)

        # make sure the signals are registered now
        import topobank_publication.signals  # noqa: F401
