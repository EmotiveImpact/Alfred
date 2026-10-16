/** Owner-only people administration (SYS-001). The server decides every grant; these
 * helpers only shape requests and read its answers. Nothing here widens authority. */
export interface PersonGrant{source:string;capability:string;expires:number}
export interface PersonView{person_id:string;you:boolean;label:string;roles:string[];devices:number;grants:PersonGrant[]}
export interface PeopleView{epoch:number;mode:'legacy_scope'|'explicit_grants';people:PersonView[];shareable:string[]}
export interface Enrolment{code:string;expires_at:number;role:'reader';person_id:string;label:string}

const PERSON=/^person-[0-9a-f]{24}$/;

export function holds(person:PersonView,source:string,capability:string){
  return person.grants.some(g=>g.source===source&&g.capability===capability);
}

/** The path and body for one per-source switch. A person ID the server did not send is refused here too. */
export function grantRequest(person:PersonView,source:string,capability:string,epoch:number){
  if(!PERSON.test(person.person_id))throw new Error('invalid_person');
  return{path:`/desk/identity/people/${person.person_id}/grants`,
    body:{source,capability,days:30,epoch,revoke:holds(person,source,capability)}};
}

/** Everyone except the signed-in person, whose own switches are in the Sources list. */
export function others(view:PeopleView){return view.people.filter(p=>!p.you);}
