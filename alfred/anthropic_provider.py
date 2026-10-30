"""Claude through Anthropic's Messages API, on ALFRED's side of the sealed Hermes box.

``AnthropicProvider`` is the ``ModelProvider`` the relay in ``alfred.hermes_box`` calls for
each model request Hermes makes. It is the only place the Claude key is used:

* the key comes from a ``KeySource`` at the moment of each call and is dropped after it. It is
  never stored on the provider, logged, put in an error, or passed to the box;
* the call goes to one fixed host, ``api.anthropic.com``, over TLS with certificate and host
  name checks, to one fixed path, with no redirects followed;
* the reply is read up to a size limit and handed back unchanged, so the relay can charge
  the provider's own usage report.

The two places a key can live are the Mac keychain and a server's secret file or systemd
credential. Their readers come from ``alfred.keys`` once encryption step 1 is merged; until
then a source is anything with a ``read()`` method. Standard library only.
"""
from __future__ import annotations
import abc
import http.client
import re
import ssl

from .brain import BrainFailure
from .hermes_box import MAX_FRAME, MODEL_PATH, ModelProvider

HOST = 'api.anthropic.com'
API_VERSION = '2023-06-01'
MAX_REPLY = MAX_FRAME // 2
KEY_SHAPE = re.compile(r'[A-Za-z0-9_-]{20,400}')


class KeySource(abc.ABC):
    """Where the Claude key lives. ``read`` returns it for one call; nothing keeps it."""

    @abc.abstractmethod
    def read(self) -> str:
        """Return the key, or raise if it cannot be read."""


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
