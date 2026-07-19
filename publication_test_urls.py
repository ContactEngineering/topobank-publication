from django.urls import path, include

import topobank_publication.urls

urlpatterns = [
    # Topobank REST API
    path(
        "",
        include(
            [
                path(
                    "manager/",
                    include("topobank_rest_api.manager.urls", namespace="manager"),
                ),
                path(
                    "analysis/",
                    include("topobank_rest_api.analysis.urls", namespace="analysis"),
                ),
                path(
                    "users/",
                    include("topobank_rest_api.users.urls", namespace="users"),
                ),
                path(
                    "organizations/",
                    include("topobank_rest_api.organizations.urls", namespace="organizations"),
                ),
                path(
                    "authorization/",
                    include("topobank_rest_api.authorization.urls", namespace="authorization"),
                ),
                path(
                    "files/",
                    include("topobank_rest_api.files.urls", namespace="files"),
                ),
            ]
        ),
    ),
    # Publication App
    path(
        topobank_publication.urls.urlprefix,
        include(
            (topobank_publication.urls.urlpatterns, "topobank_publication")
        ),
    ),
    # Publication API
    path(
        topobank_publication.urls.urlprefix,
        include(
            (topobank_publication.urls.urlpatterns, "publication")
        ),
    ),
]
