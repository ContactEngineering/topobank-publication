from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("topobank-publication")
except PackageNotFoundError:
    __version__ = "unknown"
