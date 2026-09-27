"""Local commands: python3 -m alfred.run --help. No cloud dependencies."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import tempfile
import time
from .local import Fault, LocalCore
from .httpd import make_server


def demonstration():
    with tempfile.TemporaryDirectory(prefix='alfred-demo-') as directory:
        path=Path(directory)/'state.sqlite'
        core=LocalCore(path)
        owner=core.provision('demo','demo-owner','owner')
        source=core.provision('demo','demo-feed','source')
        now=int(time.time())
        print('Synthetic workspace. Real local persistence; no live AI or external messages.')
        print(json.dumps(core.ingest(source,{'id':'brief-1','subject':'production','kind':'briefing.changed',
             'basis':'reported','observed_at':now,'expires_at':now+600,'summary':'Synthetic schedule revision received.'})))
        proposal=core.propose(owner,{'id':'draft-1','capability':'message.draft',
                              'parameters':{'text':'Please review the synthetic schedule revision.'},'expires_at':now+600})
        core.approve(owner,'draft-1',proposal['fingerprint'])
        del core
        restarted=LocalCore(path)
        print('Restarted from the same SQLite database.')
        print(json.dumps(restarted.tick(owner)))
        print(json.dumps(restarted.state(owner)['counts']))
        print('A real local draft row was created and read back. Nothing was sent.')


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=str(Path.home()/'.local/share/alfred/local.sqlite'))
    commands=parser.add_subparsers(dest='command',required=True)
    provision=commands.add_parser('provision')
    provision.add_argument('--scope',required=True)
    provision.add_argument('--id',required=True)
    provision.add_argument('--role',choices=['owner','reader','source'],required=True)
    provision.add_argument('--ttl',type=int,default=86400)
    revoke=commands.add_parser('revoke'); revoke.add_argument('--id',required=True)
    serve=commands.add_parser('serve'); serve.add_argument('--port',type=int,default=8765)
    commands.add_parser('demo')
    args=parser.parse_args()
    try:
        if args.command=='demo':
            demonstration(); return
        core=LocalCore(args.db)
        if args.command=='provision':
            print(core.provision(args.scope,args.id,args.role,ttl=args.ttl))
        elif args.command=='revoke':
            core.revoke(args.id); print('Revoked.')
        else:
            with make_server(core,args.port) as server:
                print(f'ALFRED development API: http://127.0.0.1:{server.server_port}; Ctrl-C to stop.',flush=True)
                server.serve_forever()
    except Fault as exc:
        parser.exit(2,exc.code+'\n')
    except KeyboardInterrupt:
        pass


if __name__=='__main__':
    main()
