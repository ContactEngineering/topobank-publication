from django.urls import reverse

def test_api():
    """Test API routes"""
    assert reverse('topobank_publication:surface-publish', kwargs=dict(pk=123)) == '/go/html/publish/123/'
    assert reverse('topobank_publication:surface-publication-rate-too-high', kwargs=dict(pk=123)) == '/go/html/publish/123/publication-rate-too-high/'
    assert reverse('topobank_publication:surface-publication-error', kwargs=dict(pk=123)) == '/go/html/publish/123/publication-error/'
    assert reverse('topobank_publication:go', kwargs=dict(short_url='abc123')) == '/go/abc123/'
    assert reverse('topobank_publication:go-download', kwargs=dict(short_url='abc123')) == '/go/abc123/download/'
