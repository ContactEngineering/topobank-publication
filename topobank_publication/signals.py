import logging

import short_url
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Publication, PublicationCollection

_log = logging.getLogger(__name__)


@receiver(post_save, sender=Publication)
def set_short_url(sender, instance, created, **kwargs):
    """Set short_url on newly created publications."""
    if created and instance.short_url is None:
        instance.short_url = short_url.encode_url(instance.id)
        instance.save(update_fields=['short_url'])


@receiver(post_save, sender=PublicationCollection)
def set_short_url_publication_collection(sender, instance, created, **kwargs):
    """Set short_url on newly created publication collections."""
    if created and instance.short_url is None:
        instance.short_url = short_url.encode_url(instance.id)
        instance.save(update_fields=['short_url'])
