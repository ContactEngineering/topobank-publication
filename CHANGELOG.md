# Changelog for plugin *topobank-publication*

## 1.12.0 (2026-08-03)

- API: Publication now requires every measurement of a dataset to have been
  processed successfully *and* to have complete metadata in the sense of
  `Topography.is_metadata_complete`
- ENH: New `GET /go/publishable/<surface_id>/` endpoint reporting whether a dataset
  can be published and, if not, which measurements are holding it up and why
- ENH: New `GET /go/sitemap.xml` listing all published datasets and collections, so
  that crawlers can discover them without executing the JavaScript of the app
- ENH: Published datasets are now described as schema.org JSON-LD, served from the
  new `GET /go/<short_url>/metadata/` endpoint and by content negotiation on
  `GET /go/<short_url>/` for `application/ld+json`
- ENH: The `/go/` routes now carry signposting typed links (`cite-as`, `describedby`,
  `item`, `license`, `author`, `type`) in the HTTP `Link` header
- ENH: DataCite metadata now describes the data itself and not just its landing page:
  `contentUrl` points at the container download, `formats` reports its MIME type,
  `language` the language of the descriptive metadata, and `sizes` the container size
  once it has been built
- ENH: DataCite metadata of publications and collections now states the access
  condition (`info:eu-repo/semantics/openAccess`) next to the license
- ENH: DataCite metadata now expresses the relations between published objects:
  the version chain of a dataset (`IsNewVersionOf`/`IsPreviousVersionOf`) and the
  membership of a dataset in a collection (`IsPartOf`/`HasPart`)
- ENH: DataCite metadata now carries provenance information: the precise publication
  date (`Available`), the creation date of the dataset the publication was made from
  (`Created`), the range of measurement dates (`Collected`) and the publishing user
  as a `DataCurator` contributor
- ENH: New `update_doi_metadata` management command which regenerates the DataCite
  metadata of already minted DOIs and pushes it to DataCite, so that metadata
  improvements also reach datasets published earlier

## 1.11.0 (2026-08-02)

- ENH: OAI-PMH endpoint for metadata harvesting in Dublin Core (`oai_dc`) format
- ENH: Asynchronous creation of the container files of published datasets
- BUG: Concurrent publications are serialized; a version collision returns HTTP 409
  instead of leaving orphaned surfaces behind
- BUG: A failed publication is kept for reconciliation by `complete_dois` unless the
  DOI was definitely not created remotely
- BUG: The anonymous publication API no longer exposes the publisher's email address,
  `is_staff` or `date_joined`
- BUG: `renew_containers` follows its documented policy and tolerates storage errors
- BUG: `publish_collection` requires publisher ownership and runs in a transaction
- MAINT: Migrated from the custom plugin architecture to a standard Django application
- MAINT: Removed obsolete download functionality (`analysis:download`)
- MAINT: Use the standalone `topobank-rest-api` instead of `ce-ui`
- MAINT: User and authentication moved to `topobank-orcid`; removed the organization
  permission model
- BUILD: Changed build system to hatchling
- BUILD: Force-include the app's static files in the distribution; they were missing
  from the wheel because `.gitignore` matched `topobank_publication/static/`
- BUILD: Anchored the `static/` pattern in `.gitignore` to the repository root

## 1.10.0 (2025-12-16)

- ENH: Publication collections
- UPSTREAM: Updated for API changes in topobank 1.66.0
- TST: Datacite integration tests

## 1.9.0 (2025-07-28)

- UPSTREAM: Serializer has been moved to the `v1` module in `topobank`
- UPSTREAM: Writing container is now part of the `export_zip` module of `topobank`

## 1.8.2 (2025-04-24)

- BUG: Prevent duplicate publications

## 1.8.1 (2025-04-02)

- MAINT: Default to simple router in production
- MAINT: Removed bleach dependency

## 1.8.0 (2025-03-17)

- ENH: New publication flow
- ENH: REST API for publication

## 1.7.4 (2025-03-04)

- MAINT: Prettified error pages

## 1.7.3 (2025-03-04)

- BUG: Publisher should be person that published a digital surface twin (was
  that created it)

## 1.7.2 (2025-02-27)

- BUG: Fixing checking for access to original surface if original surface does
  not exist
- BUG: Use `PermissionDenied` rather than `PermissionError` so that permission
  errors are reported to the user

## 1.7.1 (2025-02-11)

- BUG: Fixed publishing page when measurements are missing
- BUG: Update used icons to fontawesome 6

## 1.7.0 (2024-11-13)

- MAINT: Updates for API changes in topobank 1.50.0

## 1.6.4 (2024-03-22)
 
- BUG: Fixed version discovery

## 1.6.3 (2024-03-21)

- BUILD: Changed build system to flit

## 1.6.2 (2024-03-12)

- MAINT: Compatibility with topobank 1.7.0

## 1.6.1 (2024-02-05)

- MAINT: Fixed typo in publishing screen

## 1.6.0 (2024-01-26)

- ENH: /go links return API redirect if `application/json` is requested,
  otherwise HTML redirect (#9)
- ENH: API endpoint for publication now returns download link
- BUG: Fix to /go links (#8)
- MAINT: Adding gitignore

## 1.5.0 (2024-01-20)

- MAINT: Split `publication` module from main TopoBank
- MAINT: Enforcing PEP-8 style
