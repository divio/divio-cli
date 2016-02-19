FROM debian:wheezy

RUN set -ex; \
    apt-get update -qq; \
    apt-get install -y \
        locales \
        gcc \
        make \
        zlib1g \
        zlib1g-dev \
        libssl-dev \
        git \
        ca-certificates \
        curl \
        libsqlite3-dev \
    ; \
    rm -rf /var/lib/apt/lists/*

# Build Python 2.7.11 from source
RUN set -ex; \
    curl -L https://www.python.org/ftp/python/2.7.11/Python-2.7.11.tgz | tar -xz; \
    cd Python-2.7.11; \
    ./configure --enable-shared; \
    make; \
    make install; \
    cd ..; \
    rm -rf /Python-2.7.11

# Make libpython findable
ENV LD_LIBRARY_PATH /usr/local/lib

# Install setuptools version 19.2 => https://github.com/pyinstaller/pyinstaller/issues/1781
RUN set -ex; \
    curl -L https://bootstrap.pypa.io/ez_setup.py > ez_setup.py; \
    python ez_setup.py --version=19.2

# Install pip
RUN set -ex; \
    curl -L https://pypi.python.org/packages/source/p/pip/pip-8.0.2.tar.gz | tar -xz; \
    cd pip-8.0.2; \
    python setup.py install; \
    cd ..; \
    rm -rf pip-8.0.2


COPY requirements.txt /code/requirements.txt
COPY requirements-build.txt /code/requirements-build.txt
RUN pip install virtualenv; \
    virtualenv /venv; \
    /venv/bin/pip install \
        -r /code/requirements.txt \
        -r /code/requirements-build.txt


WORKDIR /code/

# RUN ln -s /usr/local/lib/libpython2.7.so.1.0 /usr/lib/libpython2.7.so.1.0 && ldconfig


