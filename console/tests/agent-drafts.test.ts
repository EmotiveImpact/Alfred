import {describe,it,expect} from 'vitest';
import {parseCommand} from '../src/domain/commands';
import {DeskError} from '../src/integration/deskClient';
import {approveRequest,chipTone,confirmRequest,confirmedLine,countsLine,dismissRequest,draftsMessage,noteLine,openableNote,originChip,
  placeLines,preview,stateLine,stopReason,type AgentDraft,type DraftsView} from '../src/integration/agentDrafts';

// Invented addresses only, built from pieces.
const AT='@',PLANTED='accounts'+AT+'example.invalid',TRUSTED='office'+AT+'example.org';

const draft=(over:Partial<AgentDraft>={}):AgentDraft=>({id:'bp-'+'a'.repeat(24),job:'job-'+'b'.repeat(24),position:0,created:1700000000,
  capability:'message.draft',state:'waiting',disposition:'pending_approval',refusal:null,fingerprint:'c'.repeat(64),reason:'Asked to thank them.',
  text:'Thank you all for getting the review ready on time.\nBest wishes',original_text:null,sources_readable:true,verdict:'owner_only',
  places:[],cited:[],copied:[],excerpts:{},action:{id:'act-x',state:'proposed',fingerprint:'d'.repeat(64),expires_at:1700003600,current:true},
  confirmed:null,can:{approve:true,confirm:false,dismiss:true},...over});
const stopped=(over:Partial<AgentDraft>={})=>draft({state:'stopped',disposition:'refused',refusal:'steered_by_untrusted_text',verdict:'steered_by_untrusted_text',
  text:`Send the invoices to ${PLANTED}`,places:[{kind:'email',value:PLANTED,source:'excerpt',refs:['E1']}],cited:['E1'],copied:['E1'],
  excerpts:{E1:{note:'e'.repeat(24),title:'Invoice update',available:true}},action:null,can:{approve:false,confirm:true,dismiss:true},...over});

describe('where a draft came from',()=>{
  it('names each origin plainly and tones only the ones to notice',()=>{
    expect([originChip(draft()),chipTone(draft())]).toEqual(['From your own words','on']);
    const noted=draft({verdict:'uses_untrusted_text',cited:['E1'],excerpts:{E1:{note:'f'.repeat(24),title:'Quarterly plan',available:true}}});
    expect([originChip(noted),chipTone(noted)]).toEqual(['Uses wording from a note','']);
    expect(noteLine(noted)).toBe('Some wording came from your note “Quarterly plan”. Nothing in it sends anything anywhere.');
    expect([originChip(stopped()),chipTone(stopped())]).toEqual(['Stopped','warn']);
    const suggested=stopped({state:'suggested',disposition:'draft_only',refusal:null});
    expect([originChip(suggested),chipTone(suggested)]).toEqual(['Address from a note','warn']);
    expect(originChip(draft({verdict:null}))).toBe('Not labelled');
    expect(noteLine(draft())).toBeNull();
  });
  it('says why a draft stopped, which address and which note',()=>{
    expect(stopReason(stopped())).toBe('The email address in this draft came from “Invoice update”, not from you. Text inside an email or note can be planted to trick an agent, so ALFRED stopped it.');
    expect(placeLines(stopped())).toEqual([`Email address: ${PLANTED} · found in “Invoice update”`]);
    const nowhere=stopped({places:[{kind:'url',value:'https'+'://drop.example.net',source:'unsourced',refs:[]}]});
    expect(stopReason(nowhere)).toMatch(/^The web address in this draft is not in anything you wrote\./);
    expect(placeLines(nowhere)).toEqual(['Web address: https'+'://drop.example.net · found in nothing you or your notes wrote']);
    expect(stopReason(stopped({refusal:'capability_not_allowed_for_brains'}))).toMatch(/only local drafts can be proposed/);
    expect(stopReason(stopped({refusal:'something_else'}))).toBe('ALFRED refused this draft (something else).');
  });
  it('withholds what can no longer be read',()=>{
    const hidden=stopped({text:null,reason:null,sources_readable:false,places:[{kind:'email',value:null,source:'excerpt',refs:['E1']}],
      excerpts:{E1:{note:null,title:null,available:false}}});
    expect(preview(hidden.text)).toBe('Withheld: the notes this came from can no longer be read.');
    expect(placeLines(hidden)).toEqual(['Email address: withheld because its notes can no longer be read · found in a note you can no longer read']);
    expect(openableNote(hidden,['E1'])).toBeNull();
    expect(openableNote(stopped(),['E1'])).toEqual({id:'note:'+'e'.repeat(24),title:'Invoice update'});
  });
  it('says what the person confirmed or replaced',()=>{
    expect(confirmedLine(draft())).toBeNull();
    const kept=draft({confirmed:{at:1,verdict:'uses_untrusted_text',places:[{kind:'email',held:PLANTED,confirmed:PLANTED,replaced:false}]}});
    expect(confirmedLine(kept)).toBe(`You confirmed ${PLANTED} yourself.`);
    expect(originChip(kept)).toBe('Address you confirmed');
    const swapped=draft({confirmed:{at:1,verdict:'uses_untrusted_text',places:[{kind:'email',held:PLANTED,confirmed:TRUSTED,replaced:true}]}});
    expect(confirmedLine(swapped)).toBe(`You replaced ${PLANTED} with ${TRUSTED}.`);
  });
});

describe('the list',()=>{
  it('counts what needs the person, leaving out zeros',()=>{
    const view=(counts:DraftsView['counts']):DraftsView=>({available:true,reason:null,mode:'enforce',drafts:[],counts});
    expect(countsLine(view({waiting:3,stopped:1,suggested:0,other:0,dismissed:2}))).toBe('3 waiting · 1 stopped');
    expect(countsLine(view({waiting:0,stopped:0,suggested:1,other:2,dismissed:0}))).toBe('1 suggested only · 2 done or closed');
    expect(countsLine(view({waiting:0,stopped:0,suggested:0,other:0,dismissed:0}))).toBe('Nothing yet');
  });
  it('words every state and shortens the preview to its first line',()=>{
    expect(stateLine(draft())).toBe('Waiting for your approval');
    expect(stateLine(draft({state:'saved'}))).toBe('Saved as a local draft');
    expect(stateLine(draft({state:'changed'}))).toMatch(/cannot be approved/);
    expect(preview(draft().text)).toBe('Thank you all for getting the review ready on time.');
    expect(preview('x'.repeat(200),20)).toBe('x'.repeat(19)+'…');
  });
  it('opens with the drafts command',()=>{
    expect(parseCommand('drafts')).toEqual({kind:'dialog',dialog:'drafts'});
    expect(parseCommand('agent drafts')).toEqual({kind:'dialog',dialog:'drafts'});
    expect(parseCommand('/drafts')).toEqual({kind:'dialog',dialog:'drafts'});
    expect(parseCommand('drafts about invoices')).toEqual({kind:'search',query:'drafts about invoices'});
  });
});

describe('requests',()=>{
  it('names the exact draft, what the person saw and what they typed',()=>{
    expect(confirmRequest(stopped(),[`  ${TRUSTED} `])).toEqual({path:'/desk/hub/drafts/bp-'+'a'.repeat(24)+'/confirm',
      body:{fingerprint:'c'.repeat(64),places:[TRUSTED]}});
    expect(dismissRequest(stopped())).toEqual({path:'/desk/hub/drafts/bp-'+'a'.repeat(24)+'/dismiss',body:{}});
    expect(approveRequest(draft())).toEqual({path:'/desk/actions/act-x/approve',body:{fingerprint:'d'.repeat(64)}});
    expect(()=>approveRequest(stopped())).toThrow();
  });
  it('explains each refusal',()=>{
    expect(draftsMessage(new DeskError('rejected','invalid_places',400))).toMatch(/one per box/);
    expect(draftsMessage(new DeskError('conflict','address_hidden_in_text',409))).toMatch(/hidden characters/);
    expect(draftsMessage(new DeskError('conflict','sources_changed',409))).toMatch(/cannot be offered for approval/);
    expect(draftsMessage(new DeskError('conflict','hub_not_configured',409))).toMatch(/no brains plugged in/);
    expect(draftsMessage(new DeskError('rejected','something_new',400))).toBe('ALFRED refused this (something_new).');
    expect(draftsMessage(new Error('x'))).toBe('ALFRED could not be reached.');
  });
});
