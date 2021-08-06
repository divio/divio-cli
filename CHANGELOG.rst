Changelog
=========


3.13.1 (2021-08-60)
-------------------

* Renamed "project" command group to "app" - with alias for backwards compatiblity.
* Improve pipelines
* Fixed bug when pulling a database on projects with an old configuration file. 

3.13.0 (2021-07-29)
-------------------

* Improved handling of database files during pull
* Added support for docker-compose v2

3.12.0 (2021-05-05)
-------------------

* Updated dependencies which removes support for python 3.5 and python 2
* Added support for Divio zones
* Add support for branches of environments on project setup
* Added better DB error handling.
* Resolved YAML deprecation warning

3.11.0 (2021-03-17)
-------------------

* Corrected spelling error in help text
* Fix issue database issue during project setup


3.10.0 (2021-01-15)
-------------------

* Updated requirements
* Updated build and distribution pipline

3.9.1 (2020-12-04)
------------------

* added better help messages

3.9.0 (2020-10-30)
------------------

* added logging support
* added SSH support

3.8.1 (2020-08-03)
------------------

* fixed string encoding issue on two commands

3.8.0 (2020-07-16)
------------------

* renamed `.aldryn` file in a project to `.divio/conifg.json`
* renamed global configuration file as well.
* made `docker-compose.yml` files optional
* added command to recreated `.divio/config.json`
* renamed interal environment variable from `ALDRYN_HOST` to `DIVIO_HOST`


3.7.0 (2020-06-15)
------------------

* Removed docker-machine doctor test
* Added multienvironment support
* Bugfixes

3.6.0 (2020-04-14)
------------------

* Add MySQL support for projects
* Add PREFIX support for services
* Add support for new docker-compose backing services structure


3.5.1 (2020-02-17)
------------------

* Now supports python 3.8


3.5.0 (2019-04-03)
------------------

* Pin requirements
* Pin busy box image for docker test


3.4.2 (2019-02-21)
------------------

* Removed the normalization of the git urls.


3.4.1 (2019-02-21)
------------------

* Switched the git url parsing to the `giturl` package
* Rolled back the version pinning due to problems


3.4.0 (2019-02-12)
------------------

* Added remote git repository support
* Added testing
* Fixed issue on error handling while pulling files
* Removed binary builds
* Removed "cheatsheet" command


3.3.12 (2019-01-09)
-------------------

* Updated DNS check to be backwards compatible


3.3.11 (2019-01-09)
-------------------

* Updated DNS check to work with the latest busybox image. Older busybox versions must upgrade!


3.3.10 (2019-01-07)
-------------------

* Fixed windows build


3.3.9 (2019-01-07)
------------------

* Improved DNS lookup check


3.3.8 (2018-08-14)
------------------

* Ensure 'stage' argument sanity
* Use a wrapper function to determine the available environments


3.3.7 (2018-02-28)
------------------

* Show better warning if ``.aldryn`` file is missing
* DB extensions configurable via ``.aldryn`` file


3.3.5 (2018-02-21)
------------------

* Fixed bug in which Windows Docker volumes were not correctly parsed.


3.3.4 (2018-01-30)
------------------

* Fixed bug when doing ``divio project setup`` and pulling media files.


3.3.3 (2018-01-25)
------------------

* Fixed project id override for remote commands with ``--remote-id``
* Fixed uploading an addon on py3 for addons with the ``aldryn_config.py`` file


3.3.2 (2017-07-28)
------------------

* Add support for database upload from the working directory (``divio project push .. --dump-file ..``)
* Add support for taking backups with deployments with ``divio project deploy --backup``
* Add support for returning last deployment log with ``divio project deploy-log``


3.3.1 (2017-07-06)
------------------

* Minor bug fixes and automation improvements


3.3.0 (2017-07-04)
------------------

* Support for HTTP_PROXY and HTTPS_PROXY environment variables
* Support for some project commands without a local source checkout
* Experimental support for listing and setting environment variables


3.2.0 (2017-04-07)
------------------

* Make cryptography an optional dependency
* Adopt some of the outputs to the Desktop App
* Execute migration commands when running ``divio project update``
* Add support to decrypt encrypted backups with ``divio backup decrypt``
* Fix an issue on windows by specifying ``--format=gztar`` when building addons, thanks to @bertah
* More leftover renamings from ``aldryn`` to ``divio``
* Note: 3.1.0 was never released to pypi


3.0.1 (2016-11-15)
------------------

* rename remanding 'aldryn' strings with their new 'divio' counterparts


3.0.0 (2016-11-15)
------------------

* rename from aldryn-client to divio-cli
* improve ``aldryn version``: now shows more upgrade paths and more detailed information
* add script for testing unix builds on multiple linux distros


2.3.5 (2016-10-21)
------------------

* Fix bug in ``aldryn project push db``
* Harden ``aldryn project push media`` command


2.3.4 (2016-10-19)
------------------

* Add ``--noinput`` flags to push media and database commands


2.3.3 (2016-10-19)
------------------

* Add ``aldryn project import/export db`` commands
* Doctor checks can now be disabled through the global ``.aldryn`` file
* ``aldryn project update`` now detects the current git branch
* Make login status check more resilient by not relying on its own executable to be findable in `PATH`
* Fix issues with ``aldryn addon/boilerplate upload`` in Python 3
* Fix error with recursive delete on windows during project setup


2.3.2 (2016-07-05)
------------------

* enable postgis if local database supports it


2.3.1 (2016-06-06)
------------------

* Fix unicode issue in ``aldryn login``


2.3.0 (2016-06-06)
------------------

* Cleanup and improve boilerplate upload
* Boilerplate now uses ``excluded`` instead of ``protected`` to specify included files
* ``--debug`` now shows more info on API request errors
* Fix form meta in python 3 projects
* Fix CLI description for ``addon develop``


2.2.4 (2016-05-26)
------------------

* Fix an issue with quotes in the doctor's DNS check
* Test if a check exists when using ``aldryn doctor -c``


2.2.3 (2016-05-26)
------------------

* Push and pull db/media from test or live stage
* Check for login status in ``aldryn doctor``
* Fix an issue on some platforms with timeout in the doctor's DNS check
* freeze PyInstaller version to fix building the binaries


2.2.2 (2016-05-10)
------------------

* Use plain requests for media and database downloads
* Send the user agent with API requests
* Fix some python3 compatibility issues


2.2.1 (2016-04-26)
------------------

* Fix ``aldryn doctor`` failing on the ``docker-machine`` step (it's not strictly required)


2.2 (2016-04-07)
----------------

* Release binary package for Linux, OS X and Windows
* Improve ``aldryn doctor`` command
* Replaced usage of ``exit`` with ``sys.exit`` for compatibility
* Fixes an issue in local dev setup with newer Docker version (docker exec changed)


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
----------------

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
