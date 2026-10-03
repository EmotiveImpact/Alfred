import {Pause,Play,ListBullets,ArrowCounterClockwise} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
import {KnowledgeSphere} from '../scene/KnowledgeSphere';
import {type Category} from '../domain/model';
import {ConnectionGate} from './ConnectionGate';
import {PRESENCE_LABEL} from '../domain/presence';
const callouts:{category:Category;label:string}[]=[{category:'people',label:'People'},{category:'sources',label:'Sources'},{category:'projects',label:'Projects'},{category:'operations',label:'Actions'}];
export function KnowledgeStage(){
  const c=useConsole(),presence=c.presentation==='consciousness';
  return <section className={`knowledge-stage ${presence?'presence-mode':''}`} aria-label="Knowledge workspace">
    <div className="graph-view-label"><h1>{c.graphMode==='field'?'Knowledge field':'Explicit relationships'}</h1><span>{c.records.length} records · {c.relationships.length} links</span></div>
    {presence&&<div className="presence-label" data-activity={c.activity}><h1>ALFRED</h1><span role="status">{PRESENCE_LABEL[c.activity]}</span><small id="presence-description" className="sr-only">Decorative animation of observable app activity, not hidden reasoning or knowledge records.</small></div>}
    <div className="sphere-stage"><KnowledgeSphere records={c.records} relationships={c.relationships} selected={c.state.selected} onSelect={c.selectRecord} paused={c.state.paused||c.modal!==null} reducedMotion={c.reduced} quality={c.state.quality} onStatus={c.onStatus} mode={c.graphMode} resetEpoch={c.renderEpoch} presentation={c.presentation} activity={c.activity}/><ConnectionGate/>
      <div className="graph-callouts">{callouts.map(({category,label})=><button className={`graph-callout callout-${category}`} key={category} onClick={()=>c.openCategory(category)} aria-label={`Explore ${category}`}><span className="callout-copy"><strong>{label}</strong><small>{c.records.filter(r=>r.category===category).length.toString().padStart(2,'0')}</small></span><span className="callout-leader"><i/></span></button>)}</div>
    </div>
    <div className="graph-tools"><div className="segmented console-view" role="group" aria-label="Console view"><button aria-pressed={presence} aria-describedby={presence?'presence-description':undefined} title="Visual presence responding to composing, source retrieval and explicit read-aloud" onClick={()=>c.setPresentation('consciousness')}>Consciousness</button><button aria-pressed={!presence} onClick={()=>c.setPresentation('globe')}>Globe</button></div>
      {!presence&&<div className="view-tools"><span className="tool-divider"/><div className="segmented" role="group" aria-label="Graph presentation"><button aria-pressed={c.graphMode==='field'} onClick={()=>c.setGraphMode('field')}>Field</button><button aria-pressed={c.graphMode==='relationships'} onClick={()=>c.setGraphMode('relationships')}>Relationships</button></div></div>}
      <button className="tool-button" aria-label={c.state.paused?'Resume sphere motion':'Pause sphere motion'} aria-pressed={c.state.paused} onClick={()=>c.dispatch({type:'pause'})}>{c.state.paused?<Play size={14}/>:<Pause size={14}/>}</button><button className="tool-button" aria-label="Reset graph view" onClick={c.retryGraphics}><ArrowCounterClockwise size={14}/></button><button className="tool-button browse-records" onClick={()=>c.openCategory(null)}><ListBullets size={14}/>Browse</button>
    </div>
  </section>;
}
