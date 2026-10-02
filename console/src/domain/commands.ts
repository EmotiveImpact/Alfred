import {SCOPES,type Scope} from './model';
export type CommandIntent = {kind:'scope';scope:Scope}|{kind:'dialog';dialog:'brief'|'tasks'|'settings'|'handoff'|'jobs'|'memory'}|{kind:'search';query:string}|{kind:'empty'};
/** Local routing only. Unrecognised input is literal scoped search, never code. */
export function parseCommand(text:string,scopes:readonly Scope[]=SCOPES):CommandIntent {
  const value=text.trim().slice(0,500),lower=value.toLowerCase();
  if(!value)return {kind:'empty'};
  const aliases:Record<string,'brief'|'tasks'|'settings'|'handoff'|'jobs'|'memory'>={memory:'memory','/memory':'memory',statements:'memory','review memory':'memory',jobs:'jobs','/jobs':'jobs',brief:'brief','/brief':'brief',summarise:'brief',summarize:'brief',today:'brief',tasks:'tasks','/tasks':'tasks',plan:'tasks',settings:'settings','/settings':'settings',controls:'settings',build:'handoff',handoff:'handoff','/handoff':'handoff'};
  if(aliases[lower])return {kind:'dialog',dialog:aliases[lower]};
  if(scopes.includes(lower as Scope))return {kind:'scope',scope:lower as Scope};
  return {kind:'search',query:value.replace(/^search\s+/i,'')};
}
