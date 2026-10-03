import {SurfaceTrace} from './SurfaceMotion';
import {useState} from 'react';
import {Circle,MagnifyingGlass,SquaresFour,FileText,SlidersHorizontal,ShieldCheck,GearSix,ShareNetwork,List,X,PushPin} from '@phosphor-icons/react';
import {useConsole,type RailView} from '../state/ConsoleProvider';
const items=[{id:'home',label:'Home',Icon:Circle},{id:'search',label:'Search',Icon:MagnifyingGlass},{id:'knowledge',label:'Knowledge',Icon:SquaresFour},{id:'tasks',label:'Tasks',Icon:FileText},{id:'research',label:'Research',Icon:ShareNetwork},{id:'systems',label:'Systems',Icon:SlidersHorizontal},{id:'security',label:'Security',Icon:ShieldCheck},{id:'settings',label:'Settings',Icon:GearSix}] as const;
/** Pointer, keyboard and pin have independent state. CSS owns transition delays;
 * delayed React timers must not reopen a rail after the pointer has left. */
export function NavigationRail(){
  const{navigate,activeView}=useConsole();
  const[hovered,setHovered]=useState(false),[keyboardFocus,setKeyboardFocus]=useState(false);
  const[pinned,setPinned]=useState(false),[dismissed,setDismissed]=useState(false);
  const visible=pinned||(!dismissed&&(hovered||keyboardFocus));
  const collapse=()=>{setPinned(false);setHovered(false);setKeyboardFocus(false);setDismissed(true);};
  const choose=(id:RailView)=>{navigate(id);if(matchMedia('(hover: none)').matches)collapse();};
  return <aside className={`navigation-rail ${visible?'is-expanded':''}`} aria-label="Main navigation"
    onPointerEnter={e=>{if(e.pointerType!=='touch'){setHovered(true);setDismissed(false);}}}
    onPointerLeave={()=>setHovered(false)}
    onPointerDown={()=>setKeyboardFocus(false)}
    onFocusCapture={e=>{if((e.target as HTMLElement).matches(':focus-visible')){setKeyboardFocus(true);setDismissed(false);}}}
    onBlurCapture={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node))setKeyboardFocus(false);}}
    onKeyDown={e=>{if(e.key==='Escape'){collapse();e.stopPropagation();}}}>
    <div className="rail-surface"><SurfaceTrace expanded={visible}/>
      <button className="rail-brand" onClick={()=>choose('home')} aria-label="ALFRED home"><img src="./alfred-mark.jpg" alt=""/><span>ALFRED</span></button>
      <button className="rail-toggle" aria-label={visible?'Collapse navigation':'Expand navigation'} aria-expanded={visible} aria-controls="rail-menu" onClick={()=>{if(visible)collapse();else{setPinned(true);setDismissed(false);}}}>{visible?<X size={17}/>:<List size={17}/>}</button>
      <nav id="rail-menu" aria-label="Console views">{items.map(({id,label,Icon})=><button key={id} className={`rail-item ${activeView===id?'is-active':''}`} aria-current={activeView===id?'page':undefined} aria-label={label} onClick={()=>choose(id)}><span className="rail-icon"><Icon size={22} weight="thin"/></span><span className="rail-label">{label}</span></button>)}</nav>
      <div className="rail-tail"><button className={`rail-pin ${pinned?'is-pinned':''}`} aria-label={pinned?'Unpin navigation':visible?'Pin navigation':'Expand navigation'} aria-pressed={pinned} onClick={()=>{setPinned(!pinned);setDismissed(false);}}><PushPin size={16}/><span>Pin navigation</span></button><span className="rail-version">0.2</span></div>
    </div>
  </aside>;
}
