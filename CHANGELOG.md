# Changelog for plugin *topobank-publication*

## 1.9.0 (2025-07-28)

- UPSTREAM: Serializer has been moved to the `v1` module in `topobank`
- UPSTREAM: Writing container is now part of the `export_zip` module of `topobank`

## 1.8.2 (2025-04-24)

- BUG: Prevent duplicate publications

## 1.8.1 (2025-04-02)

- MAINT: Default to simple router in production
- MAINT: Removed bleach dependency

## 1.8.0 (2025-03-17)

- ENH: New publication flow
- ENH: REST API for publication

## 1.7.4 (2025-03-04)

- MAINT: Prettified error pages

## 1.7.3 (2025-03-04)

- BUG: Publisher should be person that published a digital surface twin (was
  that created it)

## 1.7.2 (2025-02-27)

- BUG: Fixing checking for access to original surface if original surface does
  not exist
- BUG: Use `PermissionDenied` rather than `PermissionError` so that permission
  errors are reported to the user

## 1.7.1 (2025-02-11)

- BUG: Fixed publishing page when measurements are missing
- BUG: Update used icons to fontawesome 6

## 1.7.0 (2024-11-13)

- MAINT: Updates for API changes in topobank 1.50.0

## 1.6.4 (2024-03-22)
 
- BUG: Fixed version discovery

## 1.6.3 (2024-03-21)

- BUILD: Changed build system to flit

## 1.6.2 (2024-03-12)

- MAINT: Compatibility with topobank 1.7.0

## 1.6.1 (2024-02-05)

- MAINT: Fixed typo in publishing screen

## 1.6.0 (2024-01-26)

- ENH: /go links return API redirect if `application/json` is requested,
  otherwise HTML redirect (#9)
- ENH: API endpoint for publication now returns download link
- BUG: Fix to /go links (#8)
- MAINT: Adding gitignore

## 1.5.0 (2024-01-20)

- MAINT: Split `publication` module from main TopoBank
- MAINT: Enforcing PEP-8 style
