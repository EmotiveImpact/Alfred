"""First-party LiveLens HTTP client used by ALFRED's opt-in policy integration.

Policy and exact capture approvals belong to alfred.livelens. Credentials belong
in the caller's private runtime; this client does not change ALFRED memory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LiveLensClient:
    def __init__(self, base_url: str, token: str, timeout: float = 10):
        url = urlsplit(base_url)
        if url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
            raise ValueError('invalid_base_url')
        if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost', '::1')):
            raise ValueError('https_or_loopback_required')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', token):
            raise ValueError('invalid_token')
        if not isinstance(timeout, (float, int)) or not 0.05 <= timeout <= 30:
            raise ValueError('invalid_timeout')
        self.base_url, self.token, self.timeout = base_url.rstrip('/'), token, timeout
        self.opener = build_opener(NoRedirect())

    def _request(self, path: str, value=None):
        body = None if value is None else json.dumps(value, ensure_ascii=False).encode('utf-8')
        if body is not None and len(body) > 1_048_576:
            raise ValueError('request_too_large')
        request = Request(self.base_url + path, data=body, headers={'Authorization': 'Bearer ' + self.token,
                          **({'Content-Type': 'application/json'} if body is not None else {})})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(2_097_153)
                if len(raw) > 2_097_152:
                    raise ValueError('response_too_large')
                return json.loads(raw)
        except HTTPError as error:
            raise RuntimeError('livelens_http_' + str(error.code)) from None
        except (URLError, TimeoutError, socket.timeout):
            raise RuntimeError('livelens_unavailable_or_timeout') from None

    def _get(self, path: str):
        return self._request(path)

    def capabilities(self):
        return self._get('/v1/capabilities')

    def sessions(self):
        return self._get('/v1/sessions')

    def search(self, query='', account=None, session=None, limit=100):
        params = {'q': query, 'limit': limit}
        if account is not None:
            params['account'] = account
        if session is not None:
            params['session'] = session
        return self._get('/v1/evidence/search?' + urlencode(params))

    def report(self, case_id):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', case_id):
            raise ValueError('invalid_case_id')
        return self._get('/v1/cases/' + quote(case_id, safe='') + '/report')

    def evidence(self, evidence_id):
        return self._get('/v1/evidence/' + self._identifier(evidence_id))

    def context(self, evidence_id, limit=25):
        return self._get('/v1/evidence/' + self._identifier(evidence_id) + '/context?' + urlencode({'limit': limit}))

    def sources(self):
        return self._get('/v1/sources')

    def job(self, job_id):
        return self._get('/v1/jobs/' + self._identifier(job_id))

    def create_job(self, value):
        return self._request('/v1/jobs', value)

    def stop_job(self, job_id):
        return self._request('/v1/jobs/' + self._identifier(job_id) + '/stop', {})

    @staticmethod
    def _identifier(value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', value):
            raise ValueError('invalid_identifier')
        return quote(value, safe='')


def main():
    parser = argparse.ArgumentParser(description='Read LiveLens evidence using a scoped API key')
    parser.add_argument('command', choices=('capabilities', 'sessions', 'search', 'report'))
    parser.add_argument('--query', default='')
    parser.add_argument('--case')
    args = parser.parse_args()
    client = LiveLensClient(os.environ['LIVELENS_URL'], os.environ['LIVELENS_TOKEN'])
    if args.command == 'search':
        result = client.search(args.query)
    elif args.command == 'report':
        if not args.case:
            parser.error('--case is required for report')
        result = client.report(args.case)
    else:
        result = getattr(client, args.command)()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
