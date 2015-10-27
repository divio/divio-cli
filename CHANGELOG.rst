Changelog
=========

Next release
------------

* Encode database dump log into utf-8 before writing the file.


2.0.2 (2015-10-21)
------------------

* Fix for local directory permissions on Linux (https://github.com/aldryn/aldryn-client/pull/98)
* Don't automatically delete a project after a failed setup.
  Users are prompted to delete the project if trying to set it up again.


2.0.1 (2015-10-14)
------------------

* Change push database / media confirmation texts to represent the actual state


2.0 (2015-10-13)
----------------

* Brand new client, entirely rewritten from scratch and now completely dockerized
* Ready for the new Aldryn baseproject (v3)
