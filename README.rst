Part of `edX code`__.

__ http://code.edx.org/

edX Django Release Utilities  |Travis|_ 
=======================================
.. |Travis| image:: https://travis-ci.org/edx/edx-django-release-util.svg?branch=master
.. _Travis: https://travis-ci.org/edx/edx-django-release-util?branch=master

Release pipeline utilities for edX independently-deployable applications (IDAs) based on Django.


Usage
-----
1. Install this package via pip: `pip install edx-django-release-util`.
2. Update your project settings, adding `'release_util'` to `INSTALLED_APPS`.


Testing
-------
1. Install the requirements: `make requirements`
2. Run the tests: `make test`


License
-------

The code in this repository is licensed under AGPL unless otherwise noted.

Please see ``LICENSE.txt`` for details.


How To Contribute
-----------------

Contributions are very welcome.

Please read `How To Contribute <https://github.com/edx/edx-platform/blob/master/CONTRIBUTING.rst>`_ for details.

Even though they were written with ``edx-platform`` in mind, the guidelines
should be followed for Open edX code in general.


Reporting Security Issues
-------------------------

Please do not report security issues in public. Please email security@edx.org.


Mailing List and IRC Channel
----------------------------

You can discuss this code in the `edx-code Google Group`__ or in the ``#edx-code`` IRC channel on Freenode.

__ https://groups.google.com/forum/#!forum/edx-code
