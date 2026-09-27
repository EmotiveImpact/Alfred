"""Original fictional Markdown fixtures. No personal or operational information."""
from pathlib import Path

SAMPLES = {
'MAP.md': ('map','Your knowledge map','Maps point to the canonical notes. This is a fictional development workspace.\n\n[[areas/Production]]\n[[areas/Knowledge]]\n[[areas/Systems]]'),
'areas/Production.md': ('map','Production','[[projects/Sample Film]]\n[[people/Sample Producer]]\n[[people/Sample Coordinator]]\n[[decisions/Opening]]\n[[decisions/Camera]]\n[[notes/Equipment]]\n[[notes/Brief]]'),
'areas/Knowledge.md': ('map','Knowledge','[[projects/Alfred]]\n[[procedures/Source Review]]\n[[procedures/Approve Draft]]\n[[notes/Research]]'),
'areas/Systems.md': ('map','Systems','[[projects/Home Node]]\n[[decisions/No External Send]]\n[[decisions/Offline Mode]]\n[[procedures/Shutdown]]\n[[notes/Connectivity]]'),
'projects/Sample Film.md': ('project','Sample film','The fictional production brings its brief, people and decisions into one view.\n\n[[people/Sample Producer]]\n[[people/Sample Coordinator]]\n[[decisions/Opening]]\n[[notes/Equipment]]'),
'projects/Alfred.md': ('project','ALFRED','The development goal is a personal intelligence layer with inspectable evidence and accountable actions. No live model is connected in this demo.\n\n[[procedures/Source Review]]\n[[procedures/Approve Draft]]\n[[decisions/No External Send]]'),
'projects/Home Node.md': ('project','Home node concept','A proposed local device gateway. No actual home or security system is connected.\n\n[[decisions/Offline Mode]]\n[[notes/Connectivity]]\n[[procedures/Shutdown]]'),
'people/Sample Producer.md': ('person','Sample producer','Fictional responsibility: review changes to the sample film brief.\n\n[[projects/Sample Film]]\n[[decisions/Opening]]'),
'people/Sample Coordinator.md': ('person','Sample coordinator','Fictional responsibility: check equipment confirmation and prepare the sample crew update.\n\n[[notes/Equipment]]\n[[procedures/Approve Draft]]'),
'decisions/Opening.md': ('decision','Monochrome opening','The fictional treatment proposes a monochrome opening. This authored note is not proof of a client approval.\n\n[[projects/Sample Film]]\n[[notes/Brief]]'),
'decisions/Camera.md': ('decision','Camera package','A reserved package is not the same as a confirmed collection. Keep the evidence current.\n\n[[notes/Equipment]]\n[[procedures/Source Review]]'),
'decisions/No External Send.md': ('decision','Drafts stay local','This release creates drafts inside Alfred only. It cannot send email or messages.\n\n[[procedures/Approve Draft]]'),
'decisions/Offline Mode.md': ('decision','Honest offline state','A disconnected feed is not a fresh observation. Show stale status rather than inventing certainty.\n\n[[notes/Connectivity]]'),
'procedures/Approve Draft.md': ('procedure','Approve a draft','Inspect the current evidence. Review the exact proposed text. Approve only that proposal. Check the local result.\n\n[[decisions/No External Send]]\n[[procedures/Source Review]]'),
'procedures/Source Review.md': ('procedure','Review the source','Check the original text, its file hash, revision and indexing time. An explicit link is a reference, not a verified factual relationship.\n\n[[notes/Research]]'),
'procedures/Shutdown.md': ('procedure','Stop and recover','Stop the foreground desk process deliberately. Stored local records survive. A closed browser does not stop the supervisor.\n\n[[notes/Connectivity]]'),
'notes/Brief.md': ('note','Creative brief','Sample requirement: a restrained monochrome opening followed by the main sequence.\n\n[[decisions/Opening]]'),
'notes/Equipment.md': ('note','Equipment check','The fictional camera package needs collection confirmation before the crew update is finalised.\n\n[[decisions/Camera]]\n[[people/Sample Coordinator]]'),
'notes/Research.md': ('note','Research inbox','One intentionally unresolved link demonstrates memory health. It does not represent a real missing document.\n\n[[Unreviewed idea]]\n[[projects/Alfred]]'),
'notes/Connectivity.md': ('note','Connection health','The local node must distinguish its last successful check from current upstream availability.\n\n[[decisions/Offline Mode]]\n[[projects/Home Node]]'),
}


def seed_vault(root):
    root=Path(root)
    if root.exists(): raise ValueError('Refusing to overwrite an existing vault')
    root.mkdir(parents=True,mode=0o700)
    for path,(kind,title,body) in SAMPLES.items():
        file=root/path;file.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with file.open('x',encoding='utf-8') as stream:
            stream.write(f'---\ntitle: {title}\ntype: {kind}\ntags: [synthetic, alfred-demo]\n---\n# {title}\n\n{body}\n')
