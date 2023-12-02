import logging
from importlib.metadata import version
__version__ = version("topobank-contact")

try:
    from topobank.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use topobank 0.92.0 or above to use this plugin!")

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

    def ready(self):
        # monkey patch surface serializer to add a 'publication' field
        from topobank.manager.serializers import SurfaceSerializer
        from .serializers import PublicationSerializer
        SurfaceSerializer.publication = PublicationSerializer(read_only=True)
        SurfaceSerializer.Meta.fields += ['publication']

        # make sure the signals are registered now
        import topobank_publication.signals

