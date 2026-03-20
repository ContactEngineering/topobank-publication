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

        # make sure the signals are registered now
        import topobank_publication.signals  # noqa: F401
