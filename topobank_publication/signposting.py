"""
Signposting typed links for published datasets.

Signposting (https://signposting.org) lets a client discover, from the landing
page alone and without parsing any HTML, what the persistent identifier of a
dataset is, where its metadata lives, where the data can be downloaded and
under which license. It is expressed as typed links in the HTTP `Link` header,
using the relation types registered for it.

See https://signposting.org/FAIR/ for the profile these links follow.
"""

from django.conf import settings
from django.urls import reverse

from .schema_org import CONTAINER_MIME_TYPE, JSONLD_CONTENT_TYPE

# The type of thing a landing page and a published dataset are, in terms
# signposting clients recognize.
LANDING_PAGE_TYPES = ["https://schema.org/AboutPage", "https://schema.org/Dataset"]


def _link(target, relation, **attributes):
    """Format one typed link for the `Link` header."""
    parts = [f"<{target}>", f'rel="{relation}"']
    parts.extend(f'{name}="{value}"' for name, value in attributes.items())
    return "; ".join(parts)


def signposting_links(publication, request):
    """
    Build the typed links describing a publication.

    Parameters
    ----------
    publication : Publication
        The publication to describe.
    request : HttpRequest
        Request used to turn the routes of this application into absolute URLs.

    Returns
    -------
    list of str
        Values for the `Link` header, one entry per link.
    """
    links = []

    # The persistent identifier to cite. Only a DOI qualifies; the short URL is
    # not a persistent identifier, so nothing is advertised while the DOI is
    # still pending.
    if publication.has_doi:
        links.append(_link(publication.doi_url, "cite-as"))

    # Where the machine-readable description of this dataset is.
    links.append(
        _link(
            request.build_absolute_uri(
                reverse(
                    "publication:metadata",
                    kwargs={"short_url": publication.short_url},
                )
            ),
            "describedby",
            type=JSONLD_CONTENT_TYPE,
        )
    )

    # Where the data itself is.
    links.append(
        _link(
            request.build_absolute_uri(
                reverse(
                    "publication:download-container",
                    kwargs={"short_url": publication.short_url},
                )
            ),
            "item",
            type=CONTAINER_MIME_TYPE,
        )
    )

    # Under which terms it may be used.
    links.append(
        _link(
            settings.CC_LICENSE_INFOS[publication.license]["legal_code_url"], "license"
        )
    )

    # Who created it. Authors without an ORCID iD have no identifier to link to.
    for author in publication.authors_json:
        if author.get("orcid_id"):
            links.append(_link(f"https://orcid.org/{author['orcid_id']}", "author"))

    # What kind of thing this is.
    links.extend(_link(type_uri, "type") for type_uri in LANDING_PAGE_TYPES)

    return links


def add_signposting(response, publication, request):
    """
    Add the signposting typed links of a publication to a response.

    Parameters
    ----------
    response : HttpResponse
        Response to add the `Link` header to. Returned for convenience.
    publication : Publication
        The publication the response is about.
    request : HttpRequest
        Request used to turn the routes of this application into absolute URLs.

    Returns
    -------
    HttpResponse
        The same response.
    """
    response["Link"] = ", ".join(signposting_links(publication, request))
    return response
