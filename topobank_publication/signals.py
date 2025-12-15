import logging

import short_url
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Publication, PublicationCollection

_log = logging.getLogger(__name__)

# Offset for short_url encoding to avoid conflicts with existing DOIs
# Configure via settings.SHORT_URL_OFFSET (default: 0)
SHORT_URL_OFFSET = getattr(settings, 'SHORT_URL_OFFSET', 0)


@receiver(post_save, sender=Publication)
def set_short_url(sender, instance, created, **kwargs):
    """Set short_url on newly created publications."""
    if created and instance.short_url is None:
        instance.short_url = short_url.encode_url(instance.id + SHORT_URL_OFFSET)
        instance.save(update_fields=['short_url'])


@receiver(post_save, sender=PublicationCollection)
def set_short_url_publication_collection(sender, instance, created, **kwargs):
    """Set short_url on newly created publication collections."""
    if created and instance.short_url is None:
        instance.short_url = short_url.encode_url(instance.id + SHORT_URL_OFFSET)
        instance.save(update_fields=['short_url'])
