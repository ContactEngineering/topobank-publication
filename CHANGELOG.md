# Changelog for plugin *topobank-publication*

<!--
Style for this changelog (keep to it so entries stay uniform):

- Newest version first. Heading `vX.Y.Z (DDMonYY)`, underlined with dashes.
  A version not yet released is headed `vX.Y.Z (not yet released)`.
- One bullet per user-visible change, at most two lines (about 200
  characters). Say what changed for the user and, if useful, why or by how
  much. Omit internals: no function, class, file or variable names, no
  environment variables, no commit or PR references.
- Start every bullet with one of: `ENH:` (new feature), `BUG:` (fix),
  `API:` (interface change), `PERF:` (speed or memory), `MAINT:`, `TST:`,
  `DOC:`, `BUILD:`, `CI:`.
- Small related fixes may share one bullet. No trailing period on bullets.
-->

v1.13.0 (04Aug26)
-----------------

- ENH: The v2 dataset API embeds a publication summary (DOI, license, authors,
  date, version, download), so the dataset list needs no request per row

v1.12.0 (03Aug26)
-----------------

- ENH: The dataset API reports the version of a dataset and how many versions
  exist, so the dataset list can say which version a row is
- API: Publishing requires every measurement of a dataset to be processed
  successfully and to have complete metadata
- ENH: A new endpoint reports whether a dataset can be published and, if not,
  which measurements hold it up and why
- ENH: A sitemap lists all published datasets and collections, so crawlers find
  them without running the app's JavaScript
- ENH: Published datasets are described as schema.org JSON-LD, served at their
  own metadata address and by content negotiation on the short link
- ENH: Short links carry signposting typed links (cite-as, describedby, item,
  license, author, type) in the HTTP Link header
- ENH: DataCite metadata describes the data itself, not just its landing page:
  download address, file format, metadata language and container size
- ENH: DataCite metadata of publications and collections states open access next
  to the license
- ENH: DataCite metadata records the version chain of a dataset and the
  membership of datasets in collections
- ENH: DataCite metadata records provenance: publication and creation dates, the
  range of measurement dates and the publishing user as data curator
- ENH: A new management command regenerates the DataCite metadata of existing
  DOIs and pushes it, so earlier publications gain these improvements

v1.11.0 (02Aug26)
-----------------

- ENH: Metadata harvesting through OAI-PMH in Dublin Core format
- ENH: The container files of published datasets are created asynchronously
- BUG: Concurrent publications are serialized; a version collision returns HTTP
  409 instead of leaving orphaned datasets behind
- BUG: A failed publication is kept for later reconciliation of its DOI unless
  the DOI was definitely not created at DataCite
- BUG: The anonymous publication API no longer exposes the publisher's email
  address, staff status or registration date
- BUG: Renewing container files follows its documented policy and tolerates
  storage errors
- BUG: A collection may only contain publications by the user creating it, and
  is created atomically
- MAINT: Migrated from the custom plugin architecture to a standard Django
  application
- MAINT: Removed obsolete download functionality
- MAINT: Uses the standalone topobank-rest-api package instead of ce-ui
- MAINT: Users and authentication moved to topobank-orcid; removed the
  organization permission model
- BUILD: Changed build system to hatchling
- BUILD: The distribution includes the app's static files again, which an
  over-broad ignore pattern had kept out of the wheel

v1.10.0 (16Dec25)
-----------------

- ENH: Publication collections
- MAINT: Updated for API changes in topobank 1.66.0
- TST: Integration tests against DataCite

v1.9.0 (28Jul25)
----------------

- MAINT: Updated for topobank, which now provides the publication serializer
  in its v1 API and writes the dataset containers

v1.8.2 (24Apr25)
----------------

- BUG: Prevent duplicate publications

v1.8.1 (02Apr25)
----------------

- MAINT: In production the API no longer serves a browsable index of its
  routes
- MAINT: Removed the bleach dependency

v1.8.0 (17Mar25)
----------------

- ENH: New publication flow
- ENH: REST API for publication

v1.7.4 (04Mar25)
----------------

- MAINT: Prettified error pages

v1.7.3 (04Mar25)
----------------

- BUG: The publisher is the person who published a digital surface twin, not
  the person who created it

v1.7.2 (27Feb25)
----------------

- BUG: Fixed the access check when the original dataset no longer exists
- BUG: Permission errors are reported to the user

v1.7.1 (11Feb25)
----------------

- BUG: Fixed the publishing page when measurements are missing
- BUG: Updated icons to FontAwesome 6

v1.7.0 (13Nov24)
----------------

- MAINT: Updated for API changes in topobank 1.50.0

v1.6.4 (22Mar24)
----------------

- BUG: Fixed detection of the package version

v1.6.3 (21Mar24)
----------------

- BUILD: Changed build system to flit

v1.6.2 (12Mar24)
----------------

- MAINT: Compatibility with topobank 1.7.0

v1.6.1 (05Feb24)
----------------

- MAINT: Fixed a typo in the publishing screen

v1.6.0 (26Jan24)
----------------

- ENH: Short links redirect to the API when JSON is requested and to the web
  page otherwise, which also fixes broken short links
- ENH: The publication API returns a download link

v1.5.0 (20Jan24)
----------------

- MAINT: Split the publication module from the main TopoBank
- MAINT: Code follows PEP 8 style
