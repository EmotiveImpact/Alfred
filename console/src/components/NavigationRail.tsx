import {useEffect,useRef,useState} from 'react';
import {Circle,MagnifyingGlass,SquaresFour,FileText,SlidersHorizontal,ShieldCheck,GearSix,ShareNetwork,List,X,PushPin} from '@phosphor-icons/react';
import {useConsole,type RailView} from '../state/ConsoleProvider';
const items=[{id:'home',label:'Home',Icon:Circle},{id:'search',label:'Search',Icon:MagnifyingGlass},{id:'knowledge',label:'Knowledge',Icon:SquaresFour},{id:'tasks',label:'Tasks',Icon:FileText},{id:'research',label:'Research',Icon:ShareNetwork},{id:'systems',label:'Systems',Icon:SlidersHorizontal},{id:'security',label:'Security',Icon:ShieldCheck},{id:'settings',label:'Settings',Icon:GearSix}] as const;
/** The rail overlays on expansion. Its grid column never resizes the canvas. */
export function NavigationRail(){
  const{navigate,activeView}=useConsole();
  const[open,setOpen]=useState(false),[pinned,setPinned]=useState(false),[dismissed,setDismissed]=useState(false);
  const root=useRef<HTMLElement>(null),timer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const cancel=()=>{if(timer.current)clearTimeout(timer.current);};
  useEffect(()=>()=>cancel(),[]);
  const visible=pinned||(open&&!dismissed);
  const choose=(id:RailView)=>{navigate(id);if(matchMedia('(hover: none)').matches){setPinned(false);setOpen(false);}};
  return <aside ref={root} className={`navigation-rail ${visible?'is-expanded':''}`} aria-label="Main navigation"
    onMouseEnter={()=>{cancel();setDismissed(false);timer.current=setTimeout(()=>setOpen(true),120);}}
    onMouseLeave={()=>{cancel();setDismissed(false);timer.current=setTimeout(()=>setOpen(false),180);}}
    onFocusCapture={()=>{cancel();setOpen(true);}}
    onBlurCapture={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node)){setOpen(false);setDismissed(false);}}}
    onKeyDown={e=>{if(e.key==='Escape'){cancel();setPinned(false);setOpen(false);setDismissed(true);e.stopPropagation();}}}>
    <div className="rail-surface">
      <button className="rail-brand" onClick={()=>choose('home')} aria-label="ALFRED home"><img src="./mark.svg" alt=""/><span>ALFRED</span></button>
      <button className="rail-toggle" aria-label={visible?'Collapse navigation':'Expand navigation'} aria-expanded={visible} aria-controls="rail-menu" onClick={()=>{cancel();setPinned(!visible);setDismissed(visible);setOpen(!visible);}}>{visible?<X size={17}/>:<List size={17}/>}</button>
      <nav id="rail-menu" aria-label="Console views">{items.map(({id,label,Icon})=><button key={id} className={`rail-item ${activeView===id?'is-active':''}`} aria-current={activeView===id?'page':undefined} aria-label={label} onClick={()=>choose(id)}><span className="rail-icon"><Icon size={22} weight="thin"/></span><span className="rail-label">{label}</span></button>)}</nav>
      <div className="rail-tail"><button className={`rail-pin ${pinned?'is-pinned':''}`} aria-label={pinned?'Unpin navigation':visible?'Pin navigation':'Expand navigation'} aria-pressed={pinned} onClick={()=>{setPinned(!pinned);setDismissed(false);}}><PushPin size={16}/><span>Pin navigation</span></button><span className="rail-version">0.2</span></div>
    </div>
  </aside>;
}
