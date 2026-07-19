from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from .models import Publication
from django.conf import settings


def _add_error(root, code, message):
    error = SubElement(root, 'error', code=code)
    error.text = message


def _get_base_url(request):
    return request.build_absolute_uri(request.path)


def oai_pmh_view(request):
    verb = request.GET.get('verb')
    response_date = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    root = Element('OAI-PMH', {
        'xmlns': 'http://www.openarchives.org/OAI/2.0/',
        'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsi:schemaLocation': 'http://www.openarchives.org/OAI/2.0/ http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd'
    })

    SubElement(root, 'responseDate').text = response_date
    request_elem = SubElement(root, 'request')
    request_elem.text = _get_base_url(request)

    for key, value in request.GET.items():
        request_elem.set(key, value)

    if not verb:
        _add_error(root, 'badVerb', 'Value of the verb argument is not a legal OAI-PMH verb, '
                                    'the verb argument is missing, or the verb argument is repeated.')
        return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='text/xml')

    if verb == 'Identify':
        identify = SubElement(root, 'Identify')
        SubElement(identify, 'repositoryName').text = 'contact.engineering publications'
        SubElement(identify, 'baseURL').text = _get_base_url(request)
        SubElement(identify, 'protocolVersion').text = '2.0'
        SubElement(identify, 'adminEmail').text = getattr(
            settings, 'CONTACT_EMAIL_ADDRESS', 'admin@contact.engineering')

        earliest_pub = Publication.objects.order_by('datetime').first()
        earliest_date = earliest_pub.datetime.strftime("%Y-%m-%dT%H:%M:%SZ") if earliest_pub else "1970-01-01T00:00:00Z"

        SubElement(identify, 'earliestDatestamp').text = earliest_date
        SubElement(identify, 'deletedRecord').text = 'no'
        SubElement(identify, 'granularity').text = 'YYYY-MM-DDThh:mm:ssZ'

    elif verb == 'ListMetadataFormats':
        list_metadata_formats = SubElement(root, 'ListMetadataFormats')
        metadata_format = SubElement(list_metadata_formats, 'metadataFormat')
        SubElement(metadata_format, 'metadataPrefix').text = 'oai_dc'
        SubElement(metadata_format, 'schema').text = 'http://www.openarchives.org/OAI/2.0/oai_dc.xsd'
        SubElement(metadata_format, 'metadataNamespace').text = 'http://www.openarchives.org/OAI/2.0/oai_dc/'

    elif verb == 'ListSets':
        list_sets = SubElement(root, 'ListSets')
        # We can define a single set or no sets.
        # Better to return noSetHierarchy or empty ListSets? OAI-PMH allows ListSets to be empty,
        # but requires at least one if supported.
        # If no sets are supported, we should return error noSetHierarchy.
        _add_error(root, 'noSetHierarchy', 'This repository does not support sets.')
        root.remove(list_sets)

    elif verb in ['ListIdentifiers', 'ListRecords']:
        metadata_prefix = request.GET.get('metadataPrefix')
        if not metadata_prefix:
            _add_error(root, 'badArgument', 'Missing metadataPrefix argument.')
            return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='text/xml')
        if metadata_prefix != 'oai_dc':
            _add_error(root, 'cannotDisseminateFormat', f'The metadata format {metadata_prefix} is not supported.')
            return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='text/xml')

        from_date_str = request.GET.get('from')
        until_date_str = request.GET.get('until')

        pubs = Publication.objects.all().order_by('datetime')
        if from_date_str:
            try:
                from_date = parse_datetime(from_date_str)
                if not from_date:
                    raise ValueError
                pubs = pubs.filter(datetime__gte=from_date)
            except (ValueError, TypeError):
                _add_error(root, 'badArgument', 'Invalid from date format.')
                return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='text/xml')

        if until_date_str:
            try:
                until_date = parse_datetime(until_date_str)
                if not until_date:
                    raise ValueError
                pubs = pubs.filter(datetime__lte=until_date)
            except (ValueError, TypeError):
                _add_error(root, 'badArgument', 'Invalid until date format.')
                return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='text/xml')

        if not pubs.exists():
            _add_error(root, 'noRecordsMatch', 'No matching records found.')
            return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='text/xml')

        container = SubElement(root, verb)

        for pub in pubs:
            if verb == 'ListIdentifiers':
                _add_header(container, pub)
            else:
                _add_record(container, pub, request)

    elif verb == 'GetRecord':
        identifier = request.GET.get('identifier')
        metadata_prefix = request.GET.get('metadataPrefix')

        if not identifier or not metadata_prefix:
            _add_error(root, 'badArgument', 'Missing required arguments.')
            return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='text/xml')

        if metadata_prefix != 'oai_dc':
            _add_error(root, 'cannotDisseminateFormat', f'The metadata format {metadata_prefix} is not supported.')
            return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='text/xml')

        # extract short_url from identifier
        prefix = 'oai:contact.engineering:'
        if not identifier.startswith(prefix):
            _add_error(root, 'idDoesNotExist', 'Invalid identifier format.')
            return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='text/xml')

        short_url = identifier[len(prefix):]
        try:
            pub = Publication.objects.get(short_url=short_url)
            container = SubElement(root, 'GetRecord')
            _add_record(container, pub, request)
        except Publication.DoesNotExist:
            _add_error(root, 'idDoesNotExist', 'No matching record found.')

    else:
        _add_error(root, 'badVerb', 'Illegal OAI-PMH verb.')

    return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='text/xml')


def _add_header(parent, pub):
    header = SubElement(parent, 'header')
    SubElement(header, 'identifier').text = f'oai:contact.engineering:{pub.short_url}'
    SubElement(header, 'datestamp').text = pub.datetime.strftime("%Y-%m-%dT%H:%M:%SZ")


def _add_record(parent, pub, request):
    record = SubElement(parent, 'record')
    _add_header(record, pub)

    metadata = SubElement(record, 'metadata')
    dc = SubElement(metadata, 'oai_dc:dc', {
        'xmlns:oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
        'xmlns:dc': 'http://purl.org/dc/elements/1.1/',
        'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsi:schemaLocation': 'http://www.openarchives.org/OAI/2.0/oai_dc/ '
                              'http://www.openarchives.org/OAI/2.0/oai_dc.xsd'
    })

    surface = pub.surface
    SubElement(dc, 'dc:title').text = surface.name

    for author in pub.authors_json:
        SubElement(dc, 'dc:creator').text = f"{author['first_name']} {author['last_name']}"

    SubElement(dc, 'dc:date').text = pub.datetime.strftime("%Y-%m-%d")
    SubElement(dc, 'dc:identifier').text = request.build_absolute_uri(pub.get_absolute_url())
    if pub.doi_name:
        SubElement(dc, 'dc:identifier').text = f"doi:{pub.doi_name}"

    if surface.description:
        SubElement(dc, 'dc:description').text = surface.description

    SubElement(dc, 'dc:rights').text = pub.get_license_display()
