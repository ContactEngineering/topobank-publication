"""
schema.org representation of a published dataset.

The DataCite record of a publication is only reachable through DataCite. This
module builds the equivalent description as schema.org JSON-LD, which can be
served directly from this application and embedded in its landing pages. It is
the vocabulary generic harvesters understand, from FAIR assessment tools to
Google Dataset Search.

See https://schema.org/Dataset and
https://developers.google.com/search/docs/appearance/structured-data/dataset.
"""

from django.conf import settings
from django.urls import reverse

from .models import DEFAULT_KEYWORDS

# Language of the descriptive metadata. The application is English-only, as is
# all of its guidance to authors.
METADATA_LANGUAGE = "en"

# MIME type of the published container archive, as served by the download view.
CONTAINER_MIME_TYPE = "application/zip"

# Media type this description is served as.
JSONLD_CONTENT_TYPE = "application/ld+json"

CATALOG = {
    "@type": "DataCatalog",
    "name": "contact.engineering",
    "url": "https://contact.engineering/",
}

PUBLISHER = {
    "@type": "Organization",
    "name": "contact.engineering",
    "url": "https://contact.engineering/",
}


def _creators(publication):
    """Build the list of schema.org Persons who authored the dataset."""
    creators = []
    for author in publication.authors_json:
        creator = {
            "@type": "Person",
            "name": f"{author['first_name']} {author['last_name']}",
            "givenName": author["first_name"],
            "familyName": author["last_name"],
        }
        if author.get("orcid_id"):
            creator["@id"] = f"https://orcid.org/{author['orcid_id']}"
            creator["identifier"] = f"https://orcid.org/{author['orcid_id']}"

        affiliations = []
        for affiliation in author.get("affiliations") or []:
            organization = {"@type": "Organization", "name": affiliation["name"]}
            if affiliation.get("ror_id"):
                organization["@id"] = f"https://ror.org/{affiliation['ror_id']}"
            affiliations.append(organization)
        if affiliations:
            creator["affiliation"] = affiliations

        creators.append(creator)
    return creators


def _keywords(publication):
    """Build the keyword list from the dataset tags."""
    tags = [tag.name for tag in publication.surface.tags.all()]
    return list(DEFAULT_KEYWORDS) + tags


def _collections(publication):
    """Build the list of collections this publication is part of."""
    return [
        {
            "@type": "Collection",
            "@id": collection.doi_url,
            "name": collection.title,
        }
        for collection in publication.publication_collection.exclude(
            doi_name=""
        ).order_by("pk")
    ]


def schema_org_dataset(publication, request):
    """
    Build the schema.org Dataset description of a publication.

    Parameters
    ----------
    publication : Publication
        The publication to describe.
    request : HttpRequest
        Request used to turn the routes of this application into absolute URLs.

    Returns
    -------
    dict
        JSON-LD document describing the publication as a schema.org Dataset.
    """
    surface = publication.surface
    license_infos = settings.CC_LICENSE_INFOS[publication.license]

    landing_page = request.build_absolute_uri(publication.get_absolute_url())
    download_url = request.build_absolute_uri(
        reverse(
            "publication:download-container",
            kwargs={"short_url": publication.short_url},
        )
    )
    # A DOI is the better identifier, but a publication whose DOI creation is
    # still pending has none, in which case the landing page has to serve as
    # the identifier.
    identifier = publication.doi_url or landing_page

    dataset = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "@id": identifier,
        "identifier": identifier,
        "url": landing_page,
        "name": surface.name,
        "version": str(publication.version),
        "datePublished": publication.datetime.isoformat(),
        "inLanguage": METADATA_LANGUAGE,
        "keywords": _keywords(publication),
        "creator": _creators(publication),
        "publisher": PUBLISHER,
        "provider": PUBLISHER,
        "includedInDataCatalog": CATALOG,
        "license": license_infos["legal_code_url"],
        # Access conditions are a different statement from the license: the
        # license says what may be done with the data, these say whether it can
        # be obtained at all.
        "isAccessibleForFree": True,
        "conditionsOfAccess": "open access",
        # Where the data itself can be downloaded. Without this, the document
        # describes the landing page only and gives no route to the data.
        "distribution": [
            {
                "@type": "DataDownload",
                "contentUrl": download_url,
                "encodingFormat": CONTAINER_MIME_TYPE,
            }
        ],
    }

    if surface.description:
        dataset["description"] = surface.description

    if publication.doi_url:
        # The landing page and the DOI denote the same dataset.
        dataset["sameAs"] = publication.doi_url

    collections = _collections(publication)
    if collections:
        dataset["isPartOf"] = collections

    return dataset
