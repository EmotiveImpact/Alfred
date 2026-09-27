"""Conservative, inspectable checks on cited model statements.

These rules catch certain unsupported numbers and missing monetary evidence. They
are NOT semantic entailment, a universal answer validator, or proof of truth.
Rejected text is not returned to the interface. Original source mode is unchanged.
"""
import re

NUMBER = re.compile(r'(?<!\w)\d+(?:[.,:]\d+)*(?!\w)')
MONEY = re.compile(r'(?:[£$€]\s*\d|\b(?:gbp|usd|eur)\s*\d|\d\s*(?:pounds?|dollars?|euros?|pence)\b|\b(?:free|no charge)\b)',re.I)
AMOUNT_QUESTION = re.compile(r'\b(?:price|fee|cost|budget|how much)\b',re.I)


def assess_interpretation(claims, packet):
    """Return claims plus a bounded review report. Any blocking issue withholds all.

All checks apply to text reconstructed by validate_interpretation, not arbitrary
model-supplied quotes. Completeness and truth remain unverified even with no flags.
"""
    issues=[];clean=[]
    for index, claim in enumerate(claims):
        unique={}
        for cite in claim['citations']:
            key=(cite['source_id'],cite['start_line'],cite['end_line'])
            unique.setdefault(key,cite)
        quotes='\n'.join(c['quote'] for c in unique.values())
        unsupported=sorted(set(NUMBER.findall(claim['text']))-set(NUMBER.findall(quotes)))
        if unsupported:
            issues.append({'claim_index':index,'code':'number_not_in_cited_text','blocking':True})
        if any(c['end_line']-c['start_line']+1>4 for c in unique.values()):
            issues.append({'claim_index':index,'code':'broad_citation_review','blocking':False})
        if len(unique)!=len(claim['citations']):
            issues.append({'claim_index':index,'code':'duplicate_citations_removed','blocking':False})
        clean.append({**claim,'citations':list(unique.values())})
    # Latest user question only. Earlier questions cannot turn a missing price into
    # a time answer. This detects absent evidence, not the meaning of every sentence.
    if claims and AMOUNT_QUESTION.search(packet['question']):
        quoted='\n'.join(c['quote'] for claim in clean for c in claim['citations'])
        if not MONEY.search(quoted):
            issues.append({'claim_index':None,'code':'requested_amount_not_evidenced','blocking':True})
    blocked=any(i['blocking'] for i in issues)
    report={'version':1,'status':'withheld_for_review' if blocked else 'limited_checks_only',
            'issues':issues,'semantic_entailment_verified':False,'real_world_truth_verified':False,
            'limits':'Literal number and monetary-evidence checks only. Paraphrase, negation, identity and conflicts still require review.'}
    return ([] if blocked else clean),report
