# edx-django-release-util
Release pipeline utilities for edX independently-deployable applications (IDAs) based on Django.

## Testing
To run tests:
`python manage.py test`

## Usage
To use in a Django application:
- Add module to requirements.txt/setup.py as a dependency *or* `pip install -e edx-django-release-util` if you have cloned the repo locally.
- Add to `INSTALLED_APPS`:
```python
INSTALLED_APPS = (
    ...
    'release_util',
)
```