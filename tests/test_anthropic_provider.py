"""Claude on ALFRED's side of the sealed Hermes box (docs/HERMES_BOX.md), offline.

A stand-in connection records what would be sent; nothing reaches the network. The key is
assembled at run time, so the public hygiene check never sees a credential-shaped literal.
"""
import http.client
import json
import unittest

from alfred.anthropic_provider import HOST, AnthropicProvider, KeySource
from alfred.brain import BrainFailure, Meter
from alfred import hermes_box as hb

KEY = 'sk' + '-ant-' + 'stand' + 'in' + '0123456789abcdefghij'


class Source(KeySource):
    def __init__(self, key=KEY, fail=False):
        self.key, self.fail, self.reads = key, fail, 0

    def read(self):
        self.reads += 1
        if self.fail:
            raise OSError(f'keychain refused {self.key}')
        return self.key


class Response:
    def __init__(self, status=200, content_type='text/event-stream; charset=utf-8', body=b'data: {}\n\n'):
        self.status, self.content_type, self.body = status, content_type, body

    def read(self, limit):
        return self.body[:limit]

    def getheader(self, name, default=None):
        return self.content_type if name == 'content-type' else default


class Connection:
    def __init__(self, response=None, fail=None):
        self.response, self.fail, self.sent, self.closed = response or Response(), fail, None, False

    def request(self, method, path, body, headers):
        if self.fail:
            raise self.fail
        self.sent = (method, path, body, dict(headers))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class ProviderTests(unittest.TestCase):
    def provider(self, connection, source=None):
        self.timeouts = []

        def connect(timeout):
            self.timeouts.append(timeout)
            return connection
        return AnthropicProvider(source or Source(), connect=connect)

    def test_one_call_to_the_one_path_with_the_key_read_for_it(self):
        connection, source = Connection(), Source()
        provider = self.provider(connection, source)
        status, content_type, body = provider.call(b'{"model": "m"}', ('interleaved-thinking-2025-05-14',), 30.0)
        self.assertEqual((status, content_type, body), (200, 'text/event-stream', b'data: {}\n\n'))
        method, path, sent, headers = connection.sent
        self.assertEqual((method, path, sent), ('POST', '/v1/messages', b'{"model": "m"}'))
        self.assertEqual(headers, {'content-type': 'application/json', 'anthropic-version': '2023-06-01',
                                   'x-api-key': KEY, 'accept': 'application/json, text/event-stream',
                                   'anthropic-beta': 'interleaved-thinking-2025-05-14'})
        self.assertEqual((self.timeouts, connection.closed, source.reads), ([30.0], True, 1))
        provider.call(b'{}', (), 5.0)
        self.assertEqual(source.reads, 2)
        self.assertNotIn(KEY, repr(vars(provider)))
        self.assertEqual(HOST, 'api.anthropic.com')
        self.assertEqual(provider.locality, 'cloud')

    def test_a_key_that_cannot_be_read_stops_the_call_without_showing_it(self):
        for source in (Source(fail=True), Source(key=''), Source(key='has space in it and is long enough'), Source(key=7)):
            connection = Connection()
            with self.assertRaises(BrainFailure) as caught:
                self.provider(connection, source).call(b'{}', (), 5.0)
            self.assertEqual(caught.exception.reason, 'model_key_unavailable')
            self.assertIsNone(caught.exception.__cause__)
            self.assertNotIn(KEY, str(caught.exception))
            self.assertIsNone(connection.sent)

    def test_a_network_failure_says_so_and_nothing_else(self):
        for failure in (OSError(f'refused {KEY}'), http.client.RemoteDisconnected('gone')):
            connection = Connection(fail=failure)
            with self.assertRaises(BrainFailure) as caught:
                self.provider(connection).call(b'{}', (), 5.0)
            self.assertEqual(caught.exception.reason, 'model_provider_unreachable')
            self.assertIsNone(caught.exception.__cause__)
            self.assertTrue(connection.closed)

    def test_redirects_are_refused_and_errors_passed_back(self):
        moved = self.provider(Connection(Response(status=307, content_type='text/html', body=b'moved')))
        self.assertEqual(moved.call(b'{}', (), 5.0)[0], 502)
        limited = self.provider(Connection(Response(status=429, content_type='application/json', body=b'{"x":1}')))
        self.assertEqual(limited.call(b'{}', (), 5.0), (429, 'application/json', b'{"x":1}'))

    def test_a_reply_too_large_is_refused(self):
        big = self.provider(Connection(Response(body=b'x' * (hb.MAX_FRAME // 2 + 1))))
        with self.assertRaises(BrainFailure) as caught:
            big.call(b'{}', (), 5.0)
        self.assertEqual(caught.exception.reason, 'hermes_model_reply_too_large')

    def test_through_the_relay_the_usage_report_is_charged(self):
        events = [{'type': 'message_start', 'message': {'usage': {'input_tokens': 40, 'output_tokens': 1}}},
                  {'type': 'message_delta', 'usage': {'output_tokens': 9}}]
        stream = ''.join(f'data: {json.dumps(e)}\n\n' for e in events).encode()
        meter = Meter({'wall_seconds': 30, 'tokens': 5000, 'money_pence': 0, 'steps': 5})
        relay = hb.Relay(self.provider(Connection(Response(body=stream))), meter, model='m')
        frame = {'type': 'model_request', 'id': 1, 'method': 'POST', 'path': '/v1/messages', 'betas': '',
                 'body': json.dumps({'model': 'm', 'messages': [], 'max_tokens': 100, 'stream': True})}
        self.assertEqual(relay.handle(frame)['status'], 200)
        self.assertEqual(meter.snapshot(), {'steps': 1, 'tokens': 49, 'money_pence': 0})

    def test_a_source_must_be_readable(self):
        with self.assertRaises(TypeError):
            AnthropicProvider(object())


if __name__ == '__main__':
    unittest.main()
