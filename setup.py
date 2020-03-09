#!/usr/bin/env python
import io

from setuptools import setup, find_packages

import release_util

long_description = io.open('README.rst', encoding='utf-8').read()

setup(
    name='edx-django-release-util',
    version=release_util.__version__,
    description='edx-django-release-util',
    author='edX',
    author_email='oscm@edx.org',
    long_description=long_description,
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
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Framework :: Django',
        'Framework :: Django :: 1.11',
        'Framework :: Django :: 2.0',
        'Framework :: Django :: 2.1',
        'Framework :: Django :: 2.2',
    ],
)
