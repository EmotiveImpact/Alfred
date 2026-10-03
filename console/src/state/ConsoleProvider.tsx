import {createContext,useCallback,useContext,useEffect,useMemo,useReducer,useRef,useState,type ReactNode} from 'react';
import {useReducedMotion} from 'motion/react';
import {createDemoSnapshot} from '../domain/fixtures';
import {initialState,reducer,searchRecords,SCOPES,type Category} from '../domain/model';
import {parseCommand} from '../domain/commands';
import {type GraphMode} from '../domain/projection';
import {presenceActivity} from '../domain/presence';
import {consoleMode} from '../integration/mode';
import {emptyConnectedSnapshot} from '../integration/toSnapshot';
import {useConnection,useRecordDetail} from './useConnection';
import {useAsk} from './useAsk';
import {useJobs} from './useJobs';
export type Modal='brief'|'search'|'review'|'settings'|'voice'|'handoff'|'tasks'|'records'|'security'|'ask'|'jobs'|'memory'|'routines'|null;
export type RailView='home'|'search'|'knowledge'|'tasks'|'research'|'systems'|'security'|'settings';
/** Where the executive dialog should open: a tab, or one record's details or brief. Read once, then cleared. */
export type ExecutiveTarget={view:'records'|'attention'|'insights'|'details'|'brief';id:string|null};
export function downloadJSON(value:unknown,name:string){
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function useController(){
  // Decided once from the serving origin. Connected mode never loads fixtures, even on failure.
  const[mode]=useState(()=>consoleMode());
  const[state,dispatch]=useReducer(reducer,undefined,()=>initialState(mode==='connected'?emptyConnectedSnapshot():createDemoSnapshot()));
  const[modal,setModal]=useState<Modal>(null),[query,setQuery]=useState(''),[command,setCommand]=useState('');
  const[proposalId,setProposalId]=useState<string|null>(null),[reviewConsent,setReviewConsent]=useState(false);
  const[reviewOutcome,setReviewOutcome]=useState<'reviewed'|'declined'>('reviewed');
  const[notice,setNotice]=useState(''),[renderer,setRenderer]=useState('Starting graphics');
  const[graphMode,setGraphMode]=useState<GraphMode>('field'),[activeView,setActiveView]=useState<RailView>('home');
  const[renderEpoch,setRenderEpoch]=useState(0);
  const[presentation,setPresentation]=useState<'globe'|'consciousness'>('globe');
  const[commandFocused,setCommandFocused]=useState(false),[voicePlaying,setVoicePlaying]=useState(false);
  const[executiveTarget,setExecutiveTarget]=useState<ExecutiveTarget|null>(null);
  const[memoryTab,setMemoryTab]=useState<'queue'|'asof'>('queue');
  // Lost or changed authority closes every view that could still show withdrawn material.
  const resetAsk=useRef<()=>void>(()=>{}),resetJobs=useRef<()=>void>(()=>{});
  // A change the person just made from the access panel keeps that panel open; it shows no records.
  const expectingAccessChange=useRef(false);
  const expectAccessChange=useCallback(()=>{expectingAccessChange.current=true;},[]);
  const onAuthorityLost=useCallback((kind:'cleared'|'changed')=>{
    const keep=kind==='changed'&&expectingAccessChange.current;expectingAccessChange.current=false;
    setModal(m=>keep&&m==='security'?m:null);setQuery('');setProposalId(null);setExecutiveTarget(null);setVoicePlaying(false);if(!keep)setActiveView('home');resetAsk.current();resetJobs.current();
    return keep;
  },[]);
  const live=useConnection(mode,dispatch,setNotice,onAuthorityLost);
  const connected=mode==='connected';
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
  const switchScope=useCallback((scope:string)=>{
    // In connected mode the only permitted workspaces are the ones the server issued.
    if(connected&&!live.workspaces.some(w=>w.id===scope))return;
    dispatch({type:'scope',scope});setModal(null);setQuery('');setActiveView('home');
  },[connected,live.workspaces]);
  const detail=useRecordDetail(live.client,connected,state.selected,state.snapshot.dataRevision,live.fail);
  const asking=useAsk(live.client,live.fail);resetAsk.current=asking.reset;
  const jobs=useJobs(live.client,live.fail);resetJobs.current=jobs.reset;
  const[askMode,setAskMode]=useState<'sources'|'local_model'>('sources');
  const askQuestion=(question:string,followUp=false)=>{
    // The selection is sent as context only; the server re-authorises it.
    const focusRecord=state.snapshot.records.find(r=>r.id===state.selected&&(r.origin==='authored_note'||r.origin==='reviewed_entity'));
    const mode=askMode==='local_model'&&state.snapshot.model?.allowed?'local_model':'sources';
    void asking.ask(question,{focus:focusRecord?.id??null,focusLabel:focusRecord?.title??null,mode,followUp});setModal('ask');
  };
  const openReview=(id:string,outcome:'reviewed'|'declined'='reviewed')=>{setProposalId(id);setReviewConsent(false);setReviewOutcome(outcome);setModal('review');};
  const openCategory=(category:Category|null)=>{dispatch({type:'category',category});setModal('records');};
  const openExecutive=(view:ExecutiveTarget['view'],id:string|null=null)=>{setExecutiveTarget({view,id});setModal('tasks');};
  const openMemory=(tab:'queue'|'asof'='queue')=>{setMemoryTab(tab);setModal('memory');};
  const navigate=(view:RailView)=>{
    setActiveView(view);dispatch({type:'select',id:null});
    if(view==='home'){setGraphMode('field');setModal(null);return;}
    if(view==='knowledge'){setPresentation('globe');setGraphMode('relationships');setModal(null);return;}
    if(view==='research'){switchScope('research');setActiveView('research');return;}
    if(view==='systems'){setModal('settings');return;}
    if(view==='search')setQuery('');
    setModal(view as Modal);
  };
  const runCommand=(text:string)=>{
    const intent=parseCommand(text,connected?[]:SCOPES);setCommand('');
    if(intent.kind==='empty'){inputRef.current?.focus();return;}
    // Connected: plain text asks; an explicit "search …" searches. The two stay distinct.
    if(connected&&intent.kind==='search'&&!/^\/?search\s/i.test(text.trim())){askQuestion(text.trim().slice(0,500));return;}
    if(intent.kind==='scope'){switchScope(intent.scope);return;}
    if(intent.kind==='dialog'){setModal(intent.dialog);return;}
    setQuery(intent.query);setModal('search');
  };
  const resetDemo=()=>{if(connected)return;dispatch({type:'reset',snapshot:createDemoSnapshot()});setGraphMode('field');setActiveView('home');setModal(null);setNotice('Demo reset. No external data changed.');};
  useEffect(()=>{if(!notice)return;const t=setTimeout(()=>setNotice(''),4000);return()=>clearTimeout(t);},[notice]);
  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setQuery('');setModal('search');}
    if(e.key==='Escape'&&!modal)dispatch({type:'select',id:null});};
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
  },[modal]);
  useEffect(()=>{if(modal==='search')searchRef.current?.focus();},[modal]);
  const recheckAsk=asking.recheck;
  useEffect(()=>{void recheckAsk();},[state.snapshot.dataRevision]);// eslint-disable-line react-hooks/exhaustive-deps
  const askView={state:asking.state,sessionId:asking.state.status==='done'?asking.state.sessionId:null};
  const activity=presenceActivity({connected,ready:live.connection.kind==='ready',typing:commandFocused||command.length>0,waiting:asking.state.status==='waiting',speaking:voicePlaying,reviewing:modal==='review'});
  return{presentation,setPresentation,activity,setCommandFocused,setVoicePlaying,expectAccessChange,mode,connected,live,detail,jobs,ask:askView,askQuestion,askMode,setAskMode,state,dispatch,modal,setModal,query,setQuery,command,setCommand,proposalId,reviewConsent,setReviewConsent,reviewOutcome,
    notice,setNotice,renderer,onStatus,graphMode,setGraphMode,activeView,navigate,systemReduced,reduced,inputRef,searchRef,
    records,relationships,shownRecords,selected,priorities,proposals,pending,projects,activeProposal,results,selectRecord,closeModal,
    switchScope,openReview,openCategory,runCommand,resetDemo,renderEpoch,retryGraphics:()=>setRenderEpoch(n=>n+1),
    executiveTarget,setExecutiveTarget,openExecutive,memoryTab,openMemory};
}
export type ConsoleController=ReturnType<typeof useController>;
const Context=createContext<ConsoleController|null>(null);
export function ConsoleProvider({children}:{children:ReactNode}){const controller=useController();return <Context.Provider value={controller}>{children}</Context.Provider>;}
export function useConsole(){const c=useContext(Context);if(!c)throw new Error('ConsoleProvider is missing');return c;}
