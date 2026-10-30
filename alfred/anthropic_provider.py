"""Claude through Anthropic's Messages API, on ALFRED's side of the sealed Hermes box.

``AnthropicProvider`` is the ``ModelProvider`` the relay in ``alfred.hermes_box`` calls for
each model request Hermes makes. It is the only place the Claude key is used:

* the key comes from a ``KeySource`` at the moment of each call and is dropped after it. It is
  never stored on the provider, logged, put in an error, or passed to the box;
* the call goes to one fixed host, ``api.anthropic.com``, over TLS with certificate and host
  name checks, to one fixed path, with no redirects followed;
* the reply is read up to a size limit and handed back unchanged, so the relay can charge
  the provider's own usage report.

The key lives in one of two places, read with encryption step 1's own readers
(``alfred.keys``), and never in ALFRED's keyring file:

* ``KeychainKey``: a generic password in the macOS login keychain, under the service
  ``alfred.provider.anthropic``. The owner puts it there with Apple's own tool, which asks
  for the key without echoing it, so it never appears in a command line or shell history;
* ``SecretFileKey``: a file only its owner can read, placed by a server's secret store, or
  a systemd credential by name, found in ``$CREDENTIALS_DIRECTORY`` at start.

``describe`` says where a key was found and how long it is, for the owner's check; nothing
here ever shows the key. Standard library only.
"""
from __future__ import annotations
import abc
import http.client
import re
import ssl

import os
from pathlib import Path

from .brain import BrainFailure
from .hermes_box import MAX_FRAME, MODEL_PATH, ModelProvider
from .keys import _security, read_secret_file
from .local import Fault, ident

HOST = 'api.anthropic.com'
API_VERSION = '2023-06-01'
MAX_REPLY = MAX_FRAME // 2
KEY_SHAPE = re.compile(r'[A-Za-z0-9_-]{20,400}')
KEYCHAIN_SERVICE = 'alfred.provider.anthropic'
KEY_SOURCES = ('keychain', 'file', 'credential')


class KeySource(abc.ABC):
    """Where the Claude key lives. ``read`` returns it for one call; nothing keeps it."""

    @abc.abstractmethod
    def read(self) -> str:
        """Return the key, or raise if it cannot be read."""


class KeychainKey(KeySource):
    """The key as a generic password in the macOS login keychain: service
    ``alfred.provider.anthropic``, the account given. The keychain may ask the owner once
    whether ALFRED may read it."""

    def __init__(self, account='default', *, run=None):
        self.account = ident(account)
        self._run = run or _security

    def read(self):
        return self._run(['find-generic-password', '-a', self.account, '-s', KEYCHAIN_SERVICE, '-w']).strip()

    def where(self):
        return f'login keychain item {KEYCHAIN_SERVICE} / {self.account}'


class SecretFileKey(KeySource):
    """The key in a file only its owner can read, at an absolute ``path``, or in the systemd
    credential ``credential``, found in ``$CREDENTIALS_DIRECTORY`` when it is read."""

    def __init__(self, path=None, *, credential=None, environ=None):
        if (path is None) == (credential is None):
            raise Fault('claude_key_source_unclear')
        if path is not None and not Path(path).expanduser().is_absolute():
            raise Fault('secret_file_path_not_absolute')
        self.path = None if path is None else Path(path).expanduser()
        self.credential = None if credential is None else ident(credential)
        self._environ = os.environ if environ is None else environ

    def _file(self):
        if self.path is not None:
            return self.path
        directory = self._environ.get('CREDENTIALS_DIRECTORY')
        if not directory:
            raise Fault('unlock_unavailable', 503)
        return Path(directory) / self.credential

    def read(self):
        return read_secret_file(self._file()).decode('ascii')

    def where(self):
        return f'systemd credential {self.credential}' if self.credential else f'file {self.path}'


def key_source(kind, *, account='default', path=None, credential=None, environ=None) -> KeySource:
    """The key source the owner named: ``keychain``, ``file`` (with ``path``) or
    ``credential`` (with ``credential``)."""
    if kind == 'keychain' and path is None and credential is None:
        return KeychainKey(account)
    if kind == 'file' and path is not None and credential is None:
        return SecretFileKey(path, environ=environ)
    if kind == 'credential' and credential is not None and path is None:
        return SecretFileKey(credential=credential, environ=environ)
    raise Fault('claude_key_source_unclear')


def describe(source: KeySource) -> str:
    """Where the key was found and its length, or why it was not. Never the key itself."""
    where = source.where() if callable(getattr(source, 'where', None)) else 'the key source'
    try:
        key = source.read()
    except Exception as exc:
        reason = exc.code if isinstance(exc, Fault) else type(exc).__name__
        return f'No Claude key could be read from {where} ({reason}).'
    if not isinstance(key, str) or not KEY_SHAPE.fullmatch(key):
        return f'Something is stored in {where}, but it is not in the shape of a Claude key.'
    return f'Claude key found in {where}: {len(key)} characters, in the expected shape.'


class AnthropicProvider(ModelProvider):
    locality = 'cloud'

    def __init__(self, key_source: KeySource, *, connect=None):
        if not callable(getattr(key_source, 'read', None)):
            raise TypeError('key_source needs a read() method')
        self.key_source = key_source
        self._connect = connect or (lambda timeout: http.client.HTTPSConnection(
            HOST, 443, timeout=timeout, context=ssl.create_default_context()))

    def _key(self) -> str:
        try:
            key = self.key_source.read()
        except Exception:
            raise BrainFailure('model_key_unavailable') from None
        if not isinstance(key, str) or not KEY_SHAPE.fullmatch(key):
            raise BrainFailure('model_key_unavailable')
        return key

    def call(self, body: bytes, betas: tuple, timeout: float) -> tuple:
        headers = {'content-type': 'application/json', 'anthropic-version': API_VERSION, 'x-api-key': self._key(),
                   'accept': 'application/json, text/event-stream'}
        if betas:
            headers['anthropic-beta'] = ','.join(betas)
        connection = self._connect(timeout)
        try:
            connection.request('POST', MODEL_PATH, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read(MAX_REPLY + 1)
            content_type = response.getheader('content-type', 'application/json') or 'application/json'
            status = response.status
        except (OSError, http.client.HTTPException):
            raise BrainFailure('model_provider_unreachable') from None
        finally:
            headers.clear()  # The key goes with this call.
            connection.close()
        if len(data) > MAX_REPLY:
            raise BrainFailure('hermes_model_reply_too_large')
        if 300 <= status < 400:
            return 502, 'application/json', b'{"type":"error","error":{"type":"redirect_refused"}}'
        return status, content_type.split(';')[0].strip(), data
