#!/usr/bin/env python
"""
Setup script for the edx-django-release-util package.
"""
import io
import os
import re

from setuptools import find_packages, setup


def load_requirements(*requirements_paths):
    """
    Load all requirements from the specified requirements files.

    Returns:
        list: Requirements file relative path strings
    """
    requirements = set()
    for path in requirements_paths:
        requirements.update(
            line.split('#')[0].strip() for line in open(path).readlines()
            if is_requirement(line.strip())
        )
    return list(requirements)


def is_requirement(line):
    """
    Return True if the requirement line is a package requirement.

    Returns:
        bool: True if the line is not blank, a comment, a URL, or an included file
    """
    return line and not line.startswith(('-r', '#', '-e', 'git+', '-c'))


def get_version(*file_paths):
    """
    Extract the version string from the file at the given relative path fragments.
    """
    filename = os.path.join(os.path.dirname(__file__), *file_paths)
    version_file = open(filename).read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


LONG_DESCRIPTION = open('README.rst', encoding='utf-8').read()
VERSION = get_version("release_util", "__init__.py")


setup(
    name='edx-django-release-util',
    version=VERSION,
    description='edx-django-release-util',
    author='edX',
    author_email='oscm@edx.org',
    long_description=LONG_DESCRIPTION,
    license='AGPL 3.0',
    url='http://github.com/edx/edx-django-release-util',
    install_requires=load_requirements('requirements/base.in'),
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
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Framework :: Django',
        'Framework :: Django :: 3.2',
    ],
)
