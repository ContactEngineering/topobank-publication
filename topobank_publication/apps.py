import importlib.metadata
import logging

from topobank.plugins import PluginConfig

try:
    __version__ = importlib.metadata.version('topobank-publication')
except importlib.metadata.PackageNotFoundError:
    __version__ = '0.0.0'

_log = logging.Logger(__file__)


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
        from rest_framework import serializers
        from topobank.manager.serializers import SurfaceSerializer

        SurfaceSerializer.Meta.fields += ['publication']
        SurfaceSerializer.publication = serializers.HyperlinkedRelatedField(
            view_name='publication:publication-api-detail', read_only=True)

        # make sure the signals are registered now
        import topobank_publication.signals
