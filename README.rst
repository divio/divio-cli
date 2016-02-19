#########################
Aldryn Commandline Client
#########################

|PyPI Version| |PyPI Downloads| |Wheel Support| |License|

**********
Installing
**********

``pip install aldryn-client``


****************
Using the client
****************

for more information see http://docs.aldryn.com/en/latest/tutorial/commandline/installation.html


********************
Releasing the binary
********************

All of the binaries have to be built on the operating systems they're being built for.

----
OS X
----

Native:

.. code-block:: bash

    ./scripts/build-unix


-----
Linux
-----

Native:

.. code-block:: bash

    ./scripts/build-unix

With Docker:

.. code-block:: bash

    docker-compose build
    docker-compose run --rm builder


-------
Windows
-------

Connect to a Windows VM (the only requirement is Python 2.7) and open a PowerShell

.. code-block:: powershell

    .\scripts\build-windows.ps1




.. |PyPI Version| image:: https://img.shields.io/pypi/v/aldryn-client.svg
   :target: https://pypi.python.org/pypi/aldryn-client
.. |PyPI Downloads| image:: https://img.shields.io/pypi/dm/aldryn-client.svg
   :target: https://pypi.python.org/pypi/aldryn-client
.. |Wheel Support| image:: https://img.shields.io/pypi/wheel/aldryn-client.svg
   :target: https://pypi.python.org/pypi/aldryn-client
.. |License| image:: https://img.shields.io/pypi/l/aldryn-client.svg
   :target: https://pypi.python.org/pypi/aldryn-client

