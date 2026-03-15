DataCite publication for TopoBank
=================================

Purpose
-------

This Django application adds the capability of publishing digital surface twins and assigning DOIs, managed
by DataCite. It also provides an OAI-PMH (Open Archives Initiative Protocol for Metadata Harvesting)
API endpoint to expose publication metadata using the Dublin Core (`oai_dc`) format.

Installation
------------

For production:

.. code-block:: bash

    pip install topobank-publication

For development:

Clone project, enter project directory and run

.. code-block:: bash

    pip install -e .[dev]
