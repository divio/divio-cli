import os

import attr
import struct

from cryptography.hazmat.primitives import hmac, hashes
from cryptography.hazmat.primitives.ciphers import Cipher, modes, algorithms
from cryptography.hazmat.primitives.kdf import hkdf
from cryptography.hazmat import backends


def iterchunks(data, chunksize):
    current = ''

    while True:
        nextchunk = data.read(chunksize)
        if len(nextchunk) < chunksize:
            yield current + nextchunk, True
            return
        elif current:
            yield current, False

        current = nextchunk


def minval(length):
    def validator(instance, attribute, value):
        if value < length:
            raise ValueError(
                '{} has to be >= {}'.format(attribute.name, length))
    return validator


class CipherMixin(object):
    version = 1

    # If anything below changes, the version also needs to be bumped and the
    # implementation adapted accordingly.
    header_format = b'>B16s16s16s'
    header_length = struct.calcsize(header_format)
    algorithm = algorithms.AES
    key_size = 256
    cipher_mode = modes.CTR
    auth = hmac.HMAC
    auth_hash = hashes.SHA256

    def encode_header(self, iv, salt, auth_salt):
        return struct.pack(self.header_format,
                           self.version, iv, salt, auth_salt)

    def decode_header(self, data):
        version, iv, salt, auth_salt = struct.unpack(self.header_format, data)
        assert version == self.version
        return iv, salt, auth_salt

    @classmethod
    def generate_key(self):
        return os.urandom(self.key_size / 8)

    def stretch_key(self, key, salt):
        kdf = hkdf.HKDF(
            algorithm=hashes.SHA256(),
            length=self.key_size / 8,
            salt=salt,
            info=None,
            backend=backends.default_backend()
        )
        return kdf.derive(key)


@attr.s
class StreamEncryptor(CipherMixin, object):
    key = attr.ib(repr=False)
    backend = attr.ib(default=attr.Factory(backends.default_backend))
    chunk_size = attr.ib(default=1024)
    randomness_source = attr.ib(default=os.urandom)

    def __call__(self, fh):
        iv = self.randomness_source(self.algorithm.block_size / 8)
        salt = self.randomness_source(16)
        auth_salt = self.randomness_source(16)

        key = self.stretch_key(self.key, salt)
        auth_key = self.stretch_key(self.key, auth_salt)

        encryptor = Cipher(
            self.algorithm(key),
            self.cipher_mode(iv),
            backend=self.backend,
        ).encryptor()

        auth = self.auth(
            auth_key,
            self.auth_hash(),
            backend=self.backend,
        )

        header = self.encode_header(iv, salt, auth_salt)
        auth.update(header)
        yield header

        while True:
            chunk = fh.read(self.chunk_size)
            if not chunk:
                break

            out = encryptor.update(chunk)
            auth.update(out)
            yield out

        out = encryptor.finalize()
        auth.update(out)
        yield out

        signature = auth.finalize()
        yield signature


@attr.s
class StreamDecryptor(CipherMixin, object):
    signature_length = 32

    key = attr.ib(repr=False)
    backend = attr.ib(default=attr.Factory(backends.default_backend))
    chunk_size = attr.ib(default=1024, validator=minval(signature_length))

    def __call__(self, fh):
        header = fh.read(self.header_length)
        iv, salt, auth_salt = self.decode_header(header)

        key = self.stretch_key(self.key, salt)
        auth_key = self.stretch_key(self.key, auth_salt)

        decryptor = Cipher(
            self.algorithm(key),
            self.cipher_mode(iv),
            backend=self.backend,
        ).decryptor()

        auth = self.auth(
            auth_key,
            self.auth_hash(),
            backend=self.backend,
        )

        auth.update(header)

        for chunk, islast in iterchunks(fh, self.chunk_size):
            if islast:
                chunk, signature = (
                    chunk[:-self.signature_length],
                    chunk[-self.signature_length:],
                )

            auth.update(chunk)
            yield decryptor.update(chunk)

        remainder = decryptor.finalize()
        yield remainder

        auth.verify(signature)
