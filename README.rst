########################
Divio Commandline Client
########################

|PyPI Version| |PyPI Downloads| |Wheel Support| |License|

**********
Installing
**********

``pip install divio-cli``


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




.. |PyPI Version| image:: https://img.shields.io/pypi/v/divio-cli.svg
   :target: https://pypi.python.org/pypi/divio-cli
.. |PyPI Downloads| image:: https://img.shields.io/pypi/dm/divio-cli.svg
   :target: https://pypi.python.org/pypi/divio-cli
.. |Wheel Support| image:: https://img.shields.io/pypi/wheel/divio-cli.svg
   :target: https://pypi.python.org/pypi/divio-cli
.. |License| image:: https://img.shields.io/pypi/l/divio-cli.svg
   :target: https://pypi.python.org/pypi/divio-cli

