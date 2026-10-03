"""Compare frozen packet filling with relevance floors; no model or answer keys in requests."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alfred.grounded import retrieve
from alfred.knowledge import KnowledgeStore,MarkdownVault
from alfred.policy import IdentityPolicy
from tools.evaluate_retrieval import CORPUS,QUERIES,ANSWER_KEYS,RESTRICTED,frozen_hashes

# Separate held-out fixture, evaluated only after the lexical rule was written.
# Small, same-author synthetic evidence; no claim of broad language generalisation.
HELDOUT={
 'projects/meridian.md':'# Meridian ferry\nMeridian inspection is due 18 November. [[permits]]\n',
 'projects/permits.md':'# Meridian permits\nMeridian permits require harbour approval before inspection.\n',
 'projects/cobalt.md':'# Cobalt archive\nCobalt storage limit is 40 GB.\n',
 'projects/cobalt-draft.md':'# Cobalt draft\nCobalt draft storage limit was proposed at 25 GB, not accepted.\n',
 'people/robin-east.md':'# Robin East\nRobin East owns Meridian inspections.\n',
 'people/robin-west.md':'# Robin West\nRobin West owns Cobalt retention policy.\n',
 'decisions/cobalt.md':'# Cobalt deletion\nCobalt retention is 60 days.\n',
 'personal/garden.md':'# Garden\nThe garden needs a fence inspection.\n',
 'procedures/travel.md':'# Travel expenses\nTravel receipts are reviewed every Friday.\n',
 'projects/amber.md':'# Amber exhibition\nAmber opens on 6 December.\n',
 'projects/cobalt-renewal.md':'# Cobalt renewal\nCobalt renewal notice is 45 days.\n',
 'projects/meridian-budget.md':'# Meridian budget\nMeridian approved budget is GBP 8000.\n'}
HELDOUT_QUERIES=[
 ('H01','When is Meridian inspection due?',{'projects/meridian.md'}),
 ('H02','What approval do Meridian permits require?',{'projects/permits.md'}),
 ('H03','What is the Cobalt storage limit?',{'projects/cobalt.md'}),
 ('H04','What did the Cobalt draft storage limit propose?',{'projects/cobalt-draft.md'}),
 ('H05','Who owns Meridian inspections?',{'people/robin-east.md'}),
 ('H06','What does Robin West own?',{'people/robin-west.md'}),
 ('H07','How long is Cobalt retention?',{'decisions/cobalt.md'}),
 ('H08','What does the garden need?',{'personal/garden.md'}),
 ('H09','When are travel receipts reviewed?',{'procedures/travel.md'}),
 ('H10','When does Amber open?',{'projects/amber.md'}),
 ('H11','What is the Cobalt renewal notice?',{'projects/cobalt-renewal.md'}),
 ('H12','What is the approved Meridian budget?',{'projects/meridian-budget.md'}),
 ('H13','What must Meridian do before inspection?',{'projects/permits.md'}),
 ('H14','What is Robin East responsible for?',{'people/robin-east.md'}),
 ('H15','What is the garden mortgage amortisation?',set()),
 ('H16','Who won the interplanetary chess championship?',set()),
 ('H17','What is the Amber plutonium isotope allowance?',set()),
 ('H18','What is the Cobalt lunar launch velocity?',set())]


def run(corpus,queries,repeats):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);vault=root/'vault';vault.mkdir();hidden=root/'hidden';hidden.mkdir()
        for path,body in corpus.items():
            target=vault/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(body)
        (hidden/'Private.md').write_text('# Restrictedmarker\nMeridian Cobalt private budget and storage.\n')
        store=KnowledgeStore(root/'db')
        owner=store.provision('evaluation','owner','owner')
        source=store.provision('evaluation','main','source')
        denied=store.provision('evaluation','restricted','source')
        policy=IdentityPolicy(store);policy.grant(owner,'main','read',store.now()+3600,0)
        MarkdownVault(store,source,vault).scan();MarkdownVault(store,denied,hidden).scan()
        # Fetch packets before scoring. No label table enters the request call.
        packets={p:[] for p in ('baseline','relevant')};latency={p:[] for p in packets}
        for repeat in range(repeats):
            for qid,question,_ in queries:
                for p in (('baseline','relevant') if repeat%2==0 else ('relevant','baseline')):
                    start=time.perf_counter();packet=retrieve(store,owner,question,selection_policy=p)
                    latency[p].append((time.perf_counter()-start)*1000)
                    assert 'Restrictedmarker' not in json.dumps(packet)
                    if repeat==0:packets[p].append(packet)
        report={}
        for policy_name,rows in packets.items():
            supports=hits=items=chars=0;recalls=[];empty_controls=controls=0;per=[]
            for (qid,question,label),packet in zip(queries,rows):
                actual={e['path'] for e in packet['evidence']};found=actual&label
                supports+=len(label);hits+=len(found);items+=len(actual)
                chars+=sum(len(e['excerpt']) for e in packet['evidence'])
                if label:recalls.append(len(found)/len(label))
                else:controls+=1;empty_controls+=not actual
                per.append({'id':qid,'recall':len(found)/len(label) if label else None,
                            'evidence_paths':sorted(actual),'support_paths':sorted(label)})
            times=sorted(latency[policy_name])
            report[policy_name]={'queries':len(rows),'answerable':len(recalls),'support_hits':hits,'support_count':supports,
                 'mean_recall':round(statistics.mean(recalls),4),'precision':round(hits/items,4) if items else 0,
                 'evidence_items':items,'abstention_controls':controls,'correct_abstentions':empty_controls,
                 'mean_excerpt_characters':round(chars/len(rows),1),
                 'latency_ms':{'calls':len(times),'p50':round(statistics.median(times),2),
                               'p95':round(times[math.ceil(len(times)*.95)-1],2)},
                 'denied_evidence_items':0,'per_query':per}
        return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.repeats<=10:parser.error('repeats must be 1..10')
    dev=[(qid,q, set(ANSWER_KEYS[qid]['support'])) for qid,_,q in QUERIES]
    report={'model_inference':False,'answer_keys_in_requests':False,'scope':'synthetic lexical evidence selection, not answer correctness',
            'frozen_baseline_hashes':frozen_hashes(),
            'heldout_sha256':hashlib.sha256(json.dumps([HELDOUT,[(i,q,sorted(k)) for i,q,k in HELDOUT_QUERIES]],sort_keys=True).encode()).hexdigest(),
            'runtime_sha256':hashlib.sha256(Path('alfred/grounded.py').read_bytes()).hexdigest(),
            'development':run(CORPUS,dev,args.repeats),'heldout':run(HELDOUT,HELDOUT_QUERIES,args.repeats)}
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({group:{p:{k:v for k,v in r.items() if k!='per_query'} for p,r in report[group].items()}
                      for group in ('development','heldout')},indent=2))

if __name__=='__main__':main()
