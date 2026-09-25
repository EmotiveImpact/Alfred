"""Bounded, source-linked retrieval packets. No generated answer or model egress."""
from .local import Fault


def build_packet(store,bearer,query):
    if not isinstance(query,str) or not query.strip(): raise Fault('query_required')
    data=store.knowledge(bearer,query)
    evidence=[];skipped=[];remaining=6000
    for hit in data['results'][:5]:
        try: note=store.knowledge_note(bearer,hit['id'])
        except Fault:
            skipped.append({'id':hit['id'],'reason':'source_unavailable'});continue
        if note['sha256']!=hit['sha256']:
            skipped.append({'id':hit['id'],'reason':'source_changed'});continue
        lines=note['body'].splitlines();start=max(1,hit['line']-2);end=min(len(lines),start+9)
        value='\n'.join(lines[start-1:end]);limit=min(1200,remaining);clipped=len(value)>limit
        value=value[:limit];remaining-=len(value)
        if not value: continue
        evidence.append({'id':hit['id'],'path':note['path'],'title':note['title'],'sha256':note['sha256'],
                         'revision':note['revision'],'start_line':start,'end_line':start+value.count('\n'),
                         'excerpt':value,'truncated':clipped,'basis':'authored_note_not_verified_fact'})
        if remaining<=0: break
    return {'query':query,'scope':data['scope'],'evidence':evidence,'skipped':skipped,
            'no_answer_generated':True,'content_egress':False,'retrieval':'deterministic_keyword_match',
            'limits':{'notes':5,'excerpt_characters':6000},'indexed_snapshot_only':True}
