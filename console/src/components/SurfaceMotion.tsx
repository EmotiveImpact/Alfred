import {createContext,useCallback,useContext,useEffect,useRef,type ReactNode} from 'react';
import {useConsole} from '../state/ConsoleProvider';
type Flight=(rect:DOMRect,direction:'in'|'out')=>void;
const Context=createContext<Flight>(()=>{});
/** Only decorative edges travel. No record text, screenshot or delayed authority state. */
export function SurfaceMotion({children}:{children:ReactNode}){
  const c=useConsole(),layer=useRef<HTMLDivElement>(null),animations=useRef<Animation[]>([]),clear=useCallback(()=>{animations.current.forEach(a=>a.cancel());animations.current=[];layer.current?.replaceChildren();},[]);
  const disabled=c.reduced||c.state.paused;
  const flight=useCallback<Flight>((rect,direction)=>{
    if(disabled||document.hidden||!layer.current||rect.width<1)return;
    // At most one 24-particle flight. Rapid navigation replaces obsolete effects.
    clear();const stage=document.querySelector('.sphere-stage')?.getBoundingClientRect();if(!stage)return;
    const core={x:stage.left+stage.width*.5,y:stage.top+stage.height*.46};
    for(let i=0;i<24;i++){
      const t=i/24,edge=i%4,x=rect.left+(edge===1?rect.width:edge===3?0:rect.width*t),y=rect.top+(edge===0?0:edge===2?rect.height:rect.height*t);
      const dot=document.createElement('i');dot.className='surface-particle';layer.current.appendChild(dot);
      const a=direction==='in'?core:{x,y},b=direction==='in'?{x,y}:core;
      const transform=(p:{x:number;y:number})=>`translate3d(${p.x}px,${p.y}px,0)`;
      const animation=dot.animate([{transform:transform(a),opacity:.6},{transform:transform({x:(a.x+b.x)/2+(i%2?1:-1)*24,y:(a.y+b.y)/2-24}),opacity:.6,offset:.5},{transform:transform(b),opacity:0}],{duration:direction==='in'?620:760,delay:i*5,easing:'cubic-bezier(.2,.7,.2,1)',fill:'both'});
      animation.onfinish=()=>{dot.remove();animations.current=animations.current.filter(a=>a!==animation);animation.cancel();};animations.current.push(animation);
    }
  },[disabled,clear]);
  useEffect(()=>{if(disabled)clear();const visibility=()=>{if(document.hidden)clear();};document.addEventListener('visibilitychange',visibility);return()=>{document.removeEventListener('visibilitychange',visibility);clear();};},[disabled,clear]);
  return <Context.Provider value={flight}><div ref={layer} className="surface-motion" aria-hidden="true"/>{children}</Context.Provider>;
}
export function SurfaceTrace({expanded=true}:{expanded?:boolean}){
  const ref=useRef<HTMLSpanElement>(null),flight=useContext(Context),last=useRef<DOMRect|null>(null),previous=useRef(false),launch=useRef(flight);launch.current=flight;
  useEffect(()=>{const parent=ref.current?.parentElement;if(!parent)return;const rect=parent.getBoundingClientRect();
    if(expanded&&!previous.current)launch.current(rect,'in');else if(!expanded&&previous.current&&last.current)launch.current(last.current,'out');
    previous.current=expanded;last.current=rect;
  },[expanded]);
  useEffect(()=>()=>{if(previous.current&&last.current)launch.current(last.current,'out');},[]);
  return <span ref={ref} className="surface-trace" aria-hidden="true"><i/><i/><i/><i/></span>;
}
