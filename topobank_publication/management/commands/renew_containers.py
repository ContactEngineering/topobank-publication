import logging

from django.core.management.base import BaseCommand

from topobank_publication.models import Publication

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Renew container files for published surfaces.

    Containers for published surfaces with DOI will *not* be
    recreated. These containers should not change any more.

    However, if a container for a surface with DOI is missing,
    it will be created.
    """

    def add_arguments(self, parser):

        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Just traverse publications and show what would be done.',
        )

    def handle(self, *args, **options):

        num_failed = 0
        num_success = 0
        num_skipped = 0
        num_with = 0
        num_without = 0

        num_total = Publication.objects.count()

        for pub_idx, pub in enumerate(Publication.objects.order_by('datetime')):

            #
            # Determining whether a container exists does a storage `.size` HEAD
            # request (see Publication.has_container). If the underlying object is
            # missing/unreachable this must not abort the whole run - treat it as
            # "no container" so it gets (re)created below.
            #
            try:
                has_container = pub.has_container
            except Exception as exc:
                _log.warning(
                    f"Could not determine container status for publication "
                    f"'{pub.short_url}' (id {pub.id}), reason: {exc}. "
                    f"Assuming the container is missing.")
                has_container = False

            if has_container:
                num_with += 1
            else:
                num_without += 1

            #
            # Corrected policy (matches this command's docstring):
            #  - has a container AND a DOI  -> skip (immutable, must not change)
            #  - missing its container      -> (re)create it, even if it has a DOI
            #  - otherwise (container, no DOI) -> renew
            #
            if has_container and pub.has_doi:
                num_skipped += 1
                self.stdout.write(self.style.NOTICE(
                    f"Skipping publication '{pub.short_url}', because it already has a "
                    f"DOI and a container and should not change."))
                continue

            _log.info(f"Renewing container for publication '{pub.short_url}', id {pub.id}, {pub_idx+1}/{num_total}..")
            if not options['dry_run']:
                try:
                    pub.renew_container()
                    num_success += 1
                except Exception as exc:
                    _log.warning(f"Cannot container for publication {pub.id}, reason: {exc}")
                    num_failed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Statistics before run: #with: {num_with}, #without: {num_without}"))
        self.stdout.write(self.style.SUCCESS(
            f"Statistics after run: #ok: {num_success}, #failed: {num_failed}, #skipped: {num_skipped}"))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING("This was a dry run, nothing has been changed."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
