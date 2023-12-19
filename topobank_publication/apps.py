import importlib.metadata
import logging

from topobank.plugins import PluginConfig

try:
    __version__ = importlib.metadata.version('topobank-publication')
except importlib.metadata.PackageNotFoundError:
    __version__ = 'N/A (package metadata not found)'

_log = logging.Logger(__file__)


class PublicationPluginConfig(PluginConfig):
    name = 'topobank_publication'
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
        # monkey patch surface serializer to add a 'publication' field
        from topobank.manager.serializers import SurfaceSerializer
        from .serializers import PublicationSerializer
        SurfaceSerializer.publication = PublicationSerializer(read_only=True)
        try:
            SurfaceSerializer.Meta.read_only_fields += ['publication']
        except AttributeError:
            SurfaceSerializer.Meta.read_only_fields = ['publication']

        # make sure the signals are registered now
        import topobank_publication.signals
