from rest_framework import serializers
from topobank.plugins import PluginConfig

from .version import __version__


class PublicationPluginConfig(PluginConfig):
    name = 'topobank_publication'
    label = 'publication'
    verbose_name = "Publication"

    class TopobankPluginMeta:
        name = "Publication"
        version = __version__
        description = """
        Publish digital surface twins and assign DOIs via DataCite
        """
        logo = "topobank_publication/static/images/ce_logo.svg"
        restricted = False  # Accessible for all users, without permissions

    def ready(self):
        from topobank.manager.serializers import SurfaceSerializer

        # Monkey patch the new field into the serializer
        publication_field = serializers.HyperlinkedRelatedField(
            view_name='publication:publication-api-detail', read_only=True)
        SurfaceSerializer.Meta.fields += ['publication']
        SurfaceSerializer.publication = publication_field
        SurfaceSerializer.__dict__['_declared_fields']['publication'] = publication_field

        # make sure the signals are registered now
        import topobank_publication.signals  # noqa: F401
