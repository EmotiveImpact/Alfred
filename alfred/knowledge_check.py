"""Inspect the local knowledge map. Nonzero exit on missing/broken references.

Run against an initialised development workspace; it does not launch a service,
contact a model, write notes or install a cron job.
"""
import argparse
import json
from pathlib import Path
from .desk import load_keys
from .knowledge import KnowledgeStore
from .local import Fault


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',default='~/.local/share/alfred/desk-demo')
    args=parser.parse_args();root=Path(args.data_dir).expanduser()
    try:
        if not (root/'desk.sqlite').is_file(): raise Fault('desk_not_initialised')
        store=KnowledgeStore(root/'desk.sqlite');data=store.knowledge(load_keys(root)['owner'])
        result={'counts':data['counts'],'map_health':data['map_health'],'issues':data['issues'],
                'sources':data['sources'],'paused':data['paused'],'live_ai':False}
        print(json.dumps(result,indent=2))
        bad=not data['sources'] or data['issues'] or data['map_health']['missing_map_sources'] or data['map_health']['outside_two_hops'] or any(s['status']!='ready' for s in data['sources'])
        raise SystemExit(1 if bad else 0)
    except (Fault,OSError,ValueError) as exc:
        print(json.dumps({'error':exc.code if isinstance(exc,Fault) else type(exc).__name__}))
        raise SystemExit(2) from None


if __name__=='__main__':main()
