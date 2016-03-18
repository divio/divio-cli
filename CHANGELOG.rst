Changelog
=========

2.2 (UNRELEASED)
------------------

* Release binary package for Linux, OS X and Windows
* Improve ``aldryn doctor`` command
* Replaced usage of ``exit`` with ``sys.exit`` for compatibility


2.1.7 (2016-02-19)
------------------

* Do not mangle the hostname when using the client as a library
* Fix a bug in the update notification


2.1.6 (2016-02-16)
------------------

* ``aldryn project deploy`` command
* netrc: catch errors
* netrc: fix regression introduced in 2.1.5


2.1.5 (2016-02-10)
------------------

* Fixes various bugs with Python 3 bytes vs strings


2.1.4 (2016-02-01)
------------------

* Adds a workaround for postgres hstore support


2.1.3 (2016-01-27)
------------------

* Fixes a bug in ``aldryn addon register`` where the passed args were in the wrong order


2.1.2 (2016-01-20)
------------------

* Fixes bug in version checker where it failed if there's no newer version available


2.1.1 (2016-01-20)
------------------

* PyPi errored during upload, reuploading with patch 2.1.1


2.1 (2016-01-20)
------------------

* Python 3 support (experimental)
* Automated update checker
* New command ``aldryn addon register``
* Improve ordering and grouping of ``aldryn project list``
* Introduces a system for a config file


2.0.5 (2015-12-17)
------------------

* Issue a warning instead of failing on missing boilerplate files.
* Fix ``media`` directory size calculation during ``aldryn project push media``.


2.0.4 (2015-11-05)
------------------

* Don't set DB permissions when uploading the database.


2.0.3 (2015-10-29)
------------------

* More robust push/pull commands for db and media.
* Encode database dump log into utf-8 before writing the file.


2.0.2 (2015-10-21)
------------------

* Fix for local directory permissions on Linux (https://github.com/aldryn/aldryn-client/pull/98).
* Don't automatically delete a project after a failed setup.
  Users are prompted to delete the project if trying to set it up again.


2.0.1 (2015-10-14)
------------------

* Change push database / media confirmation texts to represent the actual state.


2.0 (2015-10-13)
----------------

* Brand new client, entirely rewritten from scratch and now completely dockerized.
* Ready for the new Aldryn baseproject (v3).
