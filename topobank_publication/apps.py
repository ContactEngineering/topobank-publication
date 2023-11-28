from importlib.metadata import version
__version__ = version("topobank-contact")

try:
    from topobank.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use topobank 0.92.0 or above to use this plugin!")


class PublicationAppConfig(PluginConfig):
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
        # make sure the signals are registered now
        import topobank_publication.signals
