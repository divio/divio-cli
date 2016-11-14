Divio CLI - Commandline interface to the Divio Cloud
====================================================

[![PyPI Version](https://img.shields.io/pypi/v/divio-cli.svg)](https://pypi.python.org/pypi/divio-cli)
![PyPI Downloads](https://img.shields.io/pypi/dm/divio-cli.svg)
![Wheel Support](https://img.shields.io/pypi/wheel/divio-cli.svg)
[![License](https://img.shields.io/pypi/l/divio-cli.svg)](https://github.com/divio/divio-cli/blob/master/LICENSE.txt)

# Installing

```bash
pip install divio-cli
```

# Using the CLI

See [Divio Support: How to use the Divio command line interface](http://support.divio.com/local-development/aldryn-local/how-to-use-the-divio-command-line-interface)

# Releasing the binary

All of the binaries have to be built on the operating systems they're being built for.

## OS X

Currently only support for native builds 

### Build

```bash
./scripts/build-unix.sh
```

### Test
    
```bash
./binary/aldryn-Darwin version
```

## Linux

Can be built by using either Linux natively or with Docker on a UNIX system

### Build

#### Native

```bash
./scripts/build-unix.sh
```

#### with Docker

```bash
docker-compose build
docker-compose run --rm builder
```

### Test

#### Native

```bash
./binary/aldryn-Linux version
```

#### With Docker

```bash
./scripts/test-unix.sh
```

## Windows

Use / connect to a Windows (virtual) machine (the only requirement is Python 2.7) and open a PowerShell

### Build

```powershell
.\scripts\build-windows.ps1
```

### Test

```powershell
.\binary\aldryn-Windows version
```
