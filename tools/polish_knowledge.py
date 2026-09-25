"""Review fixes found by real browser acceptance, plus bounded retrieval hardening."""
from integrate_knowledge import replace


def main():
    replace('web/knowledge.js',"note:[440,465]", "note:[440,420]")
    replace('web/knowledge.js',"positions[n.id]=[centre[0]+Math.cos(angle)*radius,centre[1]+Math.sin(angle)*radius];", "positions[n.id]=[Math.max(80,Math.min(780,centre[0]+Math.cos(angle)*radius)),Math.max(55,Math.min(470,centre[1]+Math.sin(angle)*radius))];")
    replace('web/knowledge.js',"      g.append(svg('circle'", "      g.append(svg('rect',{x:-60,y:-18,width:120,height:52,fill:'transparent','pointer-events':'all'}),svg('circle'")
    replace('web/knowledge.js',"Not just stored. Understood in context.","Every connection. In context.")
    replace('tools/check_knowledge_browser.py',"Not just stored. Understood in context.","Every connection. In context.")
    replace('alfred/knowledge.py',"            for n in notes:\n                n['tags'], n['aliases']", "            if len(notes)>MAX_NOTES:\n                raise Fault('knowledge_view_capacity',409)\n            for n in notes:\n                n['tags'], n['aliases']")
    replace('alfred/knowledge.py',"            links, issues = [], []", "            if len(refs)>MAX_LINKS:\n                raise Fault('knowledge_link_view_capacity',409)\n            links, issues = [], []")
    replace('web/knowledge.js',"      state.data=data;state.last=Date.now();", "      const oldNote=state.data?.nodes.find(n=>n.id===state.selected);\n      const nextNote=data.nodes.find(n=>n.id===state.selected);\n      const changed=oldNote&&(!nextNote||nextNote.sha256!==oldNote.sha256);\n      state.data=data;state.last=Date.now();\n      if(changed){$('knowledge-inspector').replaceChildren();if($('detail-eyebrow').textContent.startsWith('KNOWLEDGE')){$('detail').close();$('detail-body').replaceChildren();}if(nextNote)inspect(nextNote.id);}")


if __name__=='__main__':main()
