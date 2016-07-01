#!/usr/bin/env python
import io
from setuptools import setup, find_packages


def is_requirement(line):
    """
    Return True if the requirement line is a package requirement;
    that is, it is not blank, a comment, or editable.
    """
    # Remove whitespace at the start/end of the line
    line = line.strip()

    # Skip blank lines, comments, and editable installs
    return not (
        line == '' or
        line.startswith('-r') or
        line.startswith('#') or
        line.startswith('-e') or
        line.startswith('git+')
    )


def load_requirements(*requirements_paths):
    """
    Load all requirements from the specified requirements files.
    Returns a list of requirement strings.
    """
    requirements = set()
    for path in requirements_paths:
        requirements.update(
            line.strip() for line in open(path).readlines()
            if is_requirement(line)
        )
    return list(requirements)


long_description = io.open('README.md', encoding='utf-8').read()

METADATA = dict(
    name='edx-django-release-util',
    version='0.0.1',
    description='edx-django-release-util',
    author='edX',
    author_email='oscm@edx.org',
    long_description=long_description,
    license='AGPL',
    url='http://github.com/edx/edx-django-release-util',
    install_requires=load_requirements('requirements/base.txt',),
    tests_require=load_requirements('requirements/test.txt'),
    packages=find_packages(exclude=['*.test', '*.tests']),
    include_package_data=True,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Environment :: Web Environment',
        'Topic :: Internet',
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Django',
    ],
)

if __name__ == '__main__':
    setup(**METADATA)
