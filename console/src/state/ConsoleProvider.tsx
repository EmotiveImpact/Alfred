import {createContext,useCallback,useContext,useEffect,useMemo,useReducer,useRef,useState,type ReactNode} from 'react';
import {useReducedMotion} from 'motion/react';
import {createDemoSnapshot} from '../domain/fixtures';
import {initialState,reducer,searchRecords,type Category,type Scope} from '../domain/model';
import {parseCommand} from '../domain/commands';
import {type GraphMode} from '../domain/projection';
export type Modal='brief'|'search'|'review'|'settings'|'voice'|'handoff'|'tasks'|'records'|'security'|null;
export type RailView='home'|'search'|'knowledge'|'tasks'|'research'|'systems'|'security'|'settings';
export function downloadJSON(value:unknown,name:string){
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function useController(){
  const[state,dispatch]=useReducer(reducer,undefined,()=>initialState(createDemoSnapshot()));
  const[modal,setModal]=useState<Modal>(null),[query,setQuery]=useState(''),[command,setCommand]=useState('');
  const[proposalId,setProposalId]=useState<string|null>(null),[reviewConsent,setReviewConsent]=useState(false);
  const[reviewOutcome,setReviewOutcome]=useState<'reviewed'|'declined'>('reviewed');
  const[notice,setNotice]=useState(''),[renderer,setRenderer]=useState('Starting graphics');
  const[graphMode,setGraphMode]=useState<GraphMode>('field'),[activeView,setActiveView]=useState<RailView>('home');
  const[renderEpoch,setRenderEpoch]=useState(0);
  const systemReduced=useReducedMotion(),inputRef=useRef<HTMLInputElement>(null),searchRef=useRef<HTMLInputElement>(null);
  const reduced=Boolean(systemReduced)||state.reducedMotion;
  // Deliberately depend on the immutable record arrays, not the entire snapshot.
  // Checking a task or opening a dialog must not rebuild the GPU scene.
  const records=useMemo(()=>state.snapshot.records.filter(r=>r.scope===state.scope),[state.snapshot.records,state.scope]);
  const relationships=useMemo(()=>{const ids=new Set(records.map(r=>r.id));return state.snapshot.relationships.filter(e=>ids.has(e.from)&&ids.has(e.to));},[records,state.snapshot.relationships]);
  const shownRecords=useMemo(()=>records.filter(r=>!state.category||r.category===state.category),[records,state.category]);
  const selected=records.find(r=>r.id===state.selected);
  const priorities=state.snapshot.priorities.filter(p=>p.scope===state.scope),proposals=state.snapshot.proposals.filter(p=>p.scope===state.scope);
  const pending=proposals.filter(p=>p.status==='pending'),projects=records.filter(r=>r.category==='projects');
  const activeProposal=proposals.find(p=>p.id===proposalId);
  const results=useMemo(()=>searchRecords(state.snapshot,state.scope,query),[state.snapshot.records,state.scope,query]);
  const onStatus=useCallback((status:string)=>setRenderer(status),[]);
  const selectRecord=useCallback((id:string)=>dispatch({type:'select',id}),[]);
  const closeModal=useCallback(()=>setModal(null),[]);
  const switchScope=useCallback((scope:Scope)=>{dispatch({type:'scope',scope});setModal(null);setQuery('');setActiveView('home');},[]);
  const openReview=(id:string,outcome:'reviewed'|'declined'='reviewed')=>{setProposalId(id);setReviewConsent(false);setReviewOutcome(outcome);setModal('review');};
  const openCategory=(category:Category|null)=>{dispatch({type:'category',category});setModal('records');};
  const navigate=(view:RailView)=>{
    setActiveView(view);dispatch({type:'select',id:null});
    if(view==='home'){setGraphMode('field');setModal(null);return;}
    if(view==='knowledge'){setGraphMode('relationships');setModal(null);return;}
    if(view==='research'){switchScope('research');setActiveView('research');return;}
    if(view==='systems'){setModal('settings');return;}
    if(view==='search')setQuery('');
    setModal(view as Modal);
  };
  const runCommand=(text:string)=>{
    const intent=parseCommand(text);setCommand('');
    if(intent.kind==='empty'){inputRef.current?.focus();return;}
    if(intent.kind==='scope'){switchScope(intent.scope);return;}
    if(intent.kind==='dialog'){setModal(intent.dialog);return;}
    setQuery(intent.query);setModal('search');
  };
  const resetDemo=()=>{dispatch({type:'reset',snapshot:createDemoSnapshot()});setGraphMode('field');setActiveView('home');setModal(null);setNotice('Demo reset. No external data changed.');};
  useEffect(()=>{if(!notice)return;const t=setTimeout(()=>setNotice(''),4000);return()=>clearTimeout(t);},[notice]);
  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setQuery('');setModal('search');}
    if(e.key==='Escape'&&!modal)dispatch({type:'select',id:null});};
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
  },[modal]);
  useEffect(()=>{if(modal==='search')searchRef.current?.focus();},[modal]);
  return{state,dispatch,modal,setModal,query,setQuery,command,setCommand,proposalId,reviewConsent,setReviewConsent,reviewOutcome,
    notice,setNotice,renderer,onStatus,graphMode,setGraphMode,activeView,navigate,systemReduced,reduced,inputRef,searchRef,
    records,relationships,shownRecords,selected,priorities,proposals,pending,projects,activeProposal,results,selectRecord,closeModal,
    switchScope,openReview,openCategory,runCommand,resetDemo,renderEpoch,retryGraphics:()=>setRenderEpoch(n=>n+1)};
}
export type ConsoleController=ReturnType<typeof useController>;
const Context=createContext<ConsoleController|null>(null);
export function ConsoleProvider({children}:{children:ReactNode}){const controller=useController();return <Context.Provider value={controller}>{children}</Context.Provider>;}
export function useConsole(){const c=useContext(Context);if(!c)throw new Error('ConsoleProvider is missing');return c;}
