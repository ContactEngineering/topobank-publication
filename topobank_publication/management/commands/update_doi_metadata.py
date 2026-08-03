"""
Management command for refreshing the DataCite metadata of existing DOIs.

Improvements to the generated metadata otherwise only reach DOIs that are
minted afterwards, leaving every dataset published so far with the metadata
that was generated at its publication time.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from topobank_publication.models import Publication, PublicationCollection

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Refresh the DataCite metadata of all publications and collections
    that already have a DOI.

    The metadata is regenerated from the current state of the database and
    pushed to DataCite. Records whose metadata is unchanged are skipped without
    contacting DataCite, which makes repeated runs cheap.

    Neither the landing page URL nor the state of a DOI is touched, so a
    findable DOI stays findable and keeps resolving where it did.

    The default is a dry run which only reports what would be done. You need to
    give a special switch to really update anything.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--do-it",
            action="store_true",
            dest="do_it",
            help="Really update the metadata. The default is a dry run.",
        )
        parser.add_argument(
            "--short-url",
            dest="short_url",
            help="Only update the publication or collection with this short URL. "
            "Useful for checking the result on a single record first.",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Settings related to DOI generation:")
        )
        for settings_name in [
            "PUBLICATION_URL_PREFIX",
            "PUBLICATION_DOI_PREFIX",
            "DATACITE_USERNAME",
            "DATACITE_API_URL",
        ]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{settings_name}: {getattr(settings, settings_name)}"
                )
            )

        num_updated = 0
        num_unchanged = 0
        num_failed = 0

        for queryset in self._querysets(options["short_url"]):
            for obj in queryset:
                label = f"{type(obj).__name__} '{obj.short_url}' ({obj.doi_name})"

                if not options["do_it"]:
                    # Regenerate the metadata to report whether it differs, but
                    # do not contact DataCite and do not save anything.
                    try:
                        data = obj._get_validated_metadata(obj.doi_name)
                    except Exception as exc:
                        self.stdout.write(
                            self.style.ERROR(
                                f"{label}: metadata could not be generated, "
                                f"reason: {exc}"
                            )
                        )
                        num_failed += 1
                        continue
                    if data == obj.datacite_json:
                        num_unchanged += 1
                    else:
                        num_updated += 1
                        self.stdout.write(f"{label}: would be updated")
                    continue

                try:
                    if obj.update_doi_metadata():
                        num_updated += 1
                        self.stdout.write(self.style.SUCCESS(f"{label}: updated"))
                    else:
                        num_unchanged += 1
                except Exception as exc:
                    # One bad record must not stop the run: there can be
                    # hundreds, and a failure here leaves the record as it was.
                    self.stdout.write(
                        self.style.ERROR(f"{label}: failed, reason: {exc}")
                    )
                    num_failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"#updated: {num_updated}, #unchanged: {num_unchanged}, "
                f"#failed: {num_failed}"
            )
        )

        if options["do_it"]:
            self.stdout.write(self.style.SUCCESS("Done."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "This was a dry run, nothing has been changed. "
                    "Use --do-it to really update the metadata."
                )
            )

    def _querysets(self, short_url):
        """Return the querysets of objects with a DOI, publications first."""
        publications = Publication.objects.exclude(doi_name="").order_by("datetime")
        collections = PublicationCollection.objects.exclude(doi_name="").order_by(
            "datetime"
        )
        if short_url:
            publications = publications.filter(short_url=short_url)
            collections = collections.filter(short_url=short_url)
        return [publications, collections]
