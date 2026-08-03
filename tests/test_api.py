from django.urls import reverse


def test_api():
    """Test API routes"""
    assert reverse('publication:publish') == '/go/publish/'
    assert reverse('publication:publication-readiness',
                   kwargs=dict(surface_id=123)) == '/go/publishable/123/'
    assert reverse('publication:go', kwargs=dict(short_url='abc123')) == '/go/abc123/'
    assert reverse('publication:publication-api-list') == '/go/publication/'
    assert reverse('publication:publication-api-detail', kwargs=dict(pk=123)) == '/go/publication/123/'
