"""One-time, first-party consolidation of existing product documents.

No upstream instructions or code are executed. Only the explicit documents below
are edited; original requirement IDs, source content and archived receipts remain.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE='03e946fc3fb6fe0b540abe5ff52204de6f0f99ed'
MARKER='<!-- ALFRED unified operational/executive baseline: 2026-09-27 -->'
DOCS=['docs/PRD.md','docs/PRODUCT_BRIEF.md','docs/ARCHITECTURE.md','docs/MEMORY_ARCHITECTURE.md',
      'docs/OBSIDIAN_INTEGRATION.md','docs/ROADMAP.md','docs/BUILD_PLAN.md','docs/MEMORY_SECURITY.md',
      'docs/adr/MEMORY-001.md']


def main():
    changes=[]
    for name in DOCS:
        path=ROOT/name
        if path.is_symlink():raise ValueError('Unexpected document symlink')
        raw=path.read_bytes();text=raw.decode('utf-8')
        if MARKER in text:continue
        original=subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT)
        if original!=raw:raise ValueError('Concurrent document changes need reconciliation: '+name)
        rel='../PRODUCT_POSITIONING.md' if '/adr/' in name else 'PRODUCT_POSITIONING.md'
        status=MARKER+'\n\n**Current product category: operational and executive intelligence.** '+f'See [positioning]({rel}). '
        status+='The owner-authorised development PR stack is now merged into `main`; start new work there. '
        status+='The real local backend and the newer React/Three.js console are both preserved, but the console still uses fictional fixtures and needs its authenticated backend adapter. '
        status+='Consolidation is not deployment, external integration or completion of the planned memory jobs. '
        status+='The broad source-library catalogue, not earlier archive counts, is the current inventory.\n\n'
        heading,separator,rest=text.partition('\n')
        text=heading+'\n\n'+status+rest.lstrip('\n')
        text=text.replace('ALFRED is a persistent personal and authorised operational intelligence layer.',
                          'ALFRED is operational and executive intelligence delivered through a personal AI operating environment.')
        text=text.replace('ALFRED is your persistent personal and authorised operational intelligence.',
                          'ALFRED is your operational and executive intelligence, delivered through a personal AI operating environment.')
        text=text.replace('Product baseline: local application v0.8, plus the separately developing console toolchain.',
                          'Product baseline: local application v0.8 and the functional, separately tested React/Three.js fixture console, consolidated in main.')
        text=text.replace("A newer branch contains an isolated console toolchain. Its internal 'Obsidian console' name is not evidence of an integration with the Obsidian note application. Preserve that concurrent work and the current functioning web interface.",
                          "The newer React/TypeScript/Three.js console is now present in main. Its fictional fixtures are not real backend data. Preserve this functional frontend and the existing backend-connected web interface while implementing their authenticated adapter. The internal Obsidian console name is not an Obsidian note-app integration.")
        text=text.replace('The newer console branch adds a toolchain; a finished visual implementation is not inferred from that commit.',
                          'The latest console implementation is merged and interactive, but it remains a fixture-based frontend rather than a live backend connection.')
        text=text.replace('The console branch adds an isolated UI toolchain over that baseline.',
                          'The latest functional React/Three.js fixture console is merged alongside that baseline.')
        text=text.replace('No main merge or deployment.', 'The development stack is merged into main; no deployment has occurred.')
        text=text.replace('No main merge, force-push or deployment.', 'The development stack is merged into main without force-pushing; no deployment has occurred.')
        if name=='docs/PRD.md':
            text=text.replace('## Users and operating contexts',
                '## Executive and operational outcomes\n\nExecutive intelligence covers priorities, planning, decision briefs, commitments, preparation and follow-up. Operational intelligence covers current state, source health, changes, coordination and traceable authorised outcomes. Personal knowledge and everyday usefulness remain central. Existing requirement IDs continue to apply; this positioning does not invent completed functionality.\n\n## Users and operating contexts')
            text=text.replace('Premium personal intelligence console, not an admin-dashboard default.',
                              'Premium operational and executive intelligence console, not an admin-dashboard default.')
        if name=='docs/ROADMAP.md':
            text=text.replace('Current planning branch: `research/alfred-memory-system-2026-09-27`.',
                              'Current integration baseline: `main`. The former planning branch is historical.')
            text=text.replace('Console work continues on its own branch against reviewed data contracts.',
                              'Console work starts on a new focused branch from main against reviewed data contracts. The next missing console task is the authenticated real-backend adapter, not another visual restart.')
        if name=='docs/ARCHITECTURE.md':
            text=text.replace('The newer `console/` toolchain is preserved alongside `web/`. Do not infer a completed visual implementation, note-app integration or deployment from its existence.',
                              'The functional React/Three.js `console/` implementation is preserved alongside `web/`. The console runs fictional fixture interactions; do not infer a live backend, note-app integration or deployment from the merge.')
        data=text.encode();path.write_bytes(data)
        changes.append({'path':name,'before_sha256':hashlib.sha256(raw).hexdigest(),'after_sha256':hashlib.sha256(data).hexdigest()})
    backlog_path=ROOT/'plans/memory-backlog.json'
    backlog=json.loads(backlog_path.read_text())
    backlog['product_category']='operational and executive intelligence'
    backlog['integration_branch']='main'
    backlog.setdefault('previous_baseline_commit',backlog['baseline_commit'])
    backlog['baseline_commit']=BASE
    for name in ('BUILD_START_HERE.md','docs/PRODUCT_POSITIONING.md','docs/CONSOLIDATION_2026-09-27.md','third_party/library/README.md'):
        if name not in backlog['documents']:backlog['documents'].append(name)
    backlog_path.write_text(json.dumps(backlog,indent=2)+'\n')
    registry_path=ROOT/'research/memory-sources.json';registry=json.loads(registry_path.read_text())
    registry['count_scope']='The older focused sources/ and extensions/ archives only. Broad library totals are separate and may overlap.'
    registry['broad_source_catalogue']='third_party/library/CATALOGUE.json'
    registry_path.write_text(json.dumps(registry,indent=2)+'\n')
    shelf=ROOT/'third_party/BUILD_REFERENCE_SHELF.md'
    shelf_text=shelf.read_text()
    if MARKER not in shelf_text:
        shelf.write_text(shelf_text.split('\n',1)[0]+'\n\n'+MARKER+'\n\nThis is the historical focused shelf. The broader current [source library](library/README.md) and [catalogue](library/CATALOGUE.json) cover all 42 researched repositories with actual copied/reference-only status. Start from main. Historical file counts below are preserved and overlap the broad collection.\n\n'+shelf_text.split('\n',1)[1])
    record=ROOT/'docs/CONSOLIDATION_2026-09-27.md'
    catalogue=json.loads((ROOT/'third_party/library/CATALOGUE.json').read_text())
    s=catalogue['summary']
    lines=['# ALFRED unified development baseline','', '**Operational and executive intelligence.**','',
           'On 27 September 2026 the owner explicitly authorised consolidation of all existing development PRs.',
           'The following nine PRs were merged into main with ordinary merge commits, preserving ancestry:','',
           '| PR | Work | Merge commit |','|---|---|---|',
           '| #1 | Foundation | `167e8d07c3f18299689b0bf1a21eb2d3449dfddd` |',
           '| #5 | Persistent local core | `be806434c1c351205e12d5e189bbf5007216de7c` |',
           '| #6 | Desk and knowledge | `9e1c5d1c85b21160768946f4b4e5e2e1ce1284a2` |',
           '| #7 | Grounded questions | `b44d8c9bdc60a8356e47bb2a8dd4993ce91a031b` |',
           '| #8 | OS and Pulse | `aed7044462516b2197b17820f3c1160ec27d8d02` |',
           '| #9 | Conversations | `fa16265834ad21a43f228e4cacb465a3e4af5f9d` |',
           '| #10 | Reviewed memory | `27e2c17ed57c1065fd992bb7df75cd9b6e93ab23` |',
           '| #13 | Latest premium console | `cead85d384d6a8da6417037f876cc73ac2f3a8ea` |',
           '| #12 | PRD, memory plans and focused shelf | `03e946fc3fb6fe0b540abe5ff52204de6f0f99ed` |','',
           '## Source availability','',
           f"The broad source collection covers {s['requested']} repositories: **{s['copied']} copied source-text snapshots**, **{s['reference_only']} reference-only**, **{s['error']} unresolved errors**.",
           f"It retains **{s['retained_files']:,} source-text files / {s['retained_bytes']:,} bytes**. The earlier 2,309 focused files remain separately intact; do not add overlapping file counts and call them unique code.",
           'The catalogue and per-repository manifests record exact commits, licence observations, hashes and every exclusion. These are not complete Git forks, model/data downloads or installed applications.','',
           'The original broad import ran in GitHub Actions 36290267348. Four additional root grants were manually inspected because GitHub returned NOASSERTION: OpenClaw MIT, LiveKit Apache-2.0, sqlite-vec MIT and pgvector PostgreSQL. Their exact licence hashes are recorded in the supplementary review tool.','',
           'Obsidian Headless remains an official-client reference. Its package declares UNLICENSED, which is not the permissive Unlicense. No redistribution grant was established. Other non-commercial/custom/unresolved sources are likewise not copied as unrestricted product code.','',
           '## What consolidation does not finish','',
           'The premium console and real local backend are preserved together, but remain unconnected to each other. Console fixture records are not real account information. Reviewed-memory context injection, mature identity/grants, complete retention/encryption, external connectors and voice remain planned. No private vault, external account/device, ENDSTATE or Noir was connected, and nothing was deployed.','',
           '## Validation evidence','',
           'The ALFRED unified build workflow checks plan consistency, first-party tests, exact source archives, the latest console build and browser flows. Read its actual completed results and associated PR delivery comment. This file records what was consolidated, not a prediction that future checks will pass.','',
           'Historical delivery receipts retain their original dates and branch states. Current builders start from main and BUILD_START_HERE.md. Unfinished programme issues stay open.','']
    record.write_text('\n'.join(lines))
    evidence=ROOT/'docs/evidence/unified-2026-09-27';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'document-changes.json').write_text(json.dumps({'baseline':BASE,'runtime_changed':False,'changes':changes},indent=2)+'\n')
    # Verify the actual application and console, not merely that the directories exist.
    for folder in ('alfred','web','console','tests'):
        subprocess.run(['git','diff','--exit-code',BASE,'--',folder],cwd=ROOT,check=True)
    print('Updated current category/branch instructions; retained all 27 requirement IDs and preserved runtime/console source.')

if __name__=='__main__':main()
