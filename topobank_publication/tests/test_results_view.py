import openpyxl
import tempfile

import pytest
from django.urls import reverse

from ..models import Publication

from topobank.manager.tests.utils import SurfaceFactory, UserFactory, Topography1DFactory
from topobank.analysis.tests.utils import TopographyAnalysisFactory


@pytest.fixture
def two_analyses_two_publications(test_analysis_function):
    surface1 = SurfaceFactory()
    Topography1DFactory(surface=surface1)
    surface2 = SurfaceFactory()
    Topography1DFactory(surface=surface2)
    pub1 = Publication.publish(surface1, 'cc0-1.0', surface1.creator.name)
    pub2 = Publication.publish(surface2, 'cc0-1.0', surface1.creator.name + ", " + surface2.creator.name)
    pub_topo1 = pub1.surface.topography_set.first()
    pub_topo2 = pub2.surface.topography_set.first()

    analysis1 = TopographyAnalysisFactory(subject_topography=pub_topo1, function=test_analysis_function)
    analysis2 = TopographyAnalysisFactory(subject_topography=pub_topo2, function=test_analysis_function)

    return analysis1, analysis2, pub1, pub2


@pytest.mark.django_db
def test_publication_link_in_txt_download(client, two_analyses_two_publications, handle_usage_statistics):
    (analysis1, analysis2, pub1, pub2) = two_analyses_two_publications

    #
    # Now two publications are involved in these analyses
    #
    download_url = reverse('analysis:download', kwargs=dict(ids=f"{analysis1.id},{analysis2.id}",
                                                            file_format='txt'))
    user = UserFactory(username='testuser')
    client.force_login(user)
    response = client.get(download_url)
    assert response.status_code == 200

    txt = response.content.decode()

    assert pub1.get_absolute_url() in txt
    assert pub2.get_absolute_url() in txt


@pytest.mark.django_db
def test_publication_link_in_xlsx_download(client, two_analyses_two_publications, handle_usage_statistics):
    (analysis1, analysis2, pub1, pub2) = two_analyses_two_publications

    #
    # Now two publications are involved in these analyses
    #
    download_url = reverse('analysis:download', kwargs=dict(ids=f"{analysis1.id},{analysis2.id}",
                                                            file_format='xlsx'))
    user = UserFactory()
    client.force_login(user)
    response = client.get(download_url)
    assert response.status_code == 200

    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx')  # will be deleted automatically
    tmp.write(response.content)
    tmp.seek(0)

    xlsx = openpyxl.load_workbook(tmp.name)

    sheet = xlsx['INFORMATION']
    col_B = sheet['B']
    col_B_values = [str(c.value) for c in col_B]
    assert any(pub1.get_absolute_url() in v for v in col_B_values)
    assert any(pub2.get_absolute_url() in v for v in col_B_values)
