import logging

from topobank.taskapp.celeryapp import app

_log = logging.getLogger(__name__)


@app.task
def renew_container_task(publication_id):
    from .models import Publication

    try:
        pub = Publication.objects.get(id=publication_id)
        pub.renew_container()
    except Publication.DoesNotExist:
        _log.error(
            f"Publication {publication_id} does not exist for renewing container."
        )
