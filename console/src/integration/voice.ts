/**
 * Spoken playback of an answer (VOI-001), output only. No microphone is ever requested.
 * Only voices the browser marks as on-device are used: an online voice would send the
 * text to a speech service off this machine.
 */
export interface SpokenEvidence{title:string;excerpt:string}
export interface SpokenStatement{subject:{name:string};predicate:string;value:string|null;object:{name:string}|null}
export const MAX_SPOKEN=1500;
const clean=(text:string)=>text.replace(/\[\[([^\]|]+)(\|[^\]]+)?\]\]/g,(_,target:string)=>target.split('/').pop()??target).replace(/[#*_>`]/g,'').replace(/\s+/g,' ').trim();
const sentence=(text:string)=>/[.!?…:]$/.test(text)?text:text+'.';
/** Each meaningful line as a sentence. Lines that are only links or headings markup are not read. */
const lines=(excerpt:string)=>excerpt.split('\n').filter(l=>l.replace(/\[\[[^\]]*\]\]/g,'').replace(/[#*_>`\s-]/g,'')!=='').map(l=>sentence(clean(l))).join(' ');
/** Exactly what will be spoken, built only from what the answer already shows. */
export function spokenText(question:string,evidence:readonly SpokenEvidence[],memory:readonly SpokenStatement[]=[]):string{
  const parts=[`You asked: ${sentence(clean(question))}`];
  for(const m of memory)parts.push(`Your reviewed statement: ${m.subject.name} ${m.predicate.replaceAll('_',' ')} ${m.value??m.object?.name??''}.`);
  if(evidence.length){parts.push(`${evidence.length} excerpt${evidence.length===1?'':'s'} from your notes.`);for(const e of evidence)parts.push(`From ${clean(e.title)}: ${lines(e.excerpt)}`);}
  else parts.push('Nothing you may read matched this question.');
  parts.push('These are your notes read aloud, not a generated answer.');
  const text=parts.join(' ');
  return text.length>MAX_SPOKEN?text.slice(0,MAX_SPOKEN-1).replace(/\s+\S*$/,'')+'…':text;
}
export type VoiceState='idle'|'no_local_voice'|'generated'|'playing'|'played'|'stopped'|'failed'|'acknowledged';
export const VOICE_LABEL:Record<VoiceState,string>={idle:'',no_local_voice:'No on-device voice is available in this browser, so nothing was spoken. ALFRED never uses an online voice, which would send your text off this machine.',
  generated:'Prepared exactly the text below for playback.',playing:'Playing on this device.',played:'This device reported that playback ended. That is not proof that anyone heard it.',
  stopped:'Playback was stopped before the end.',failed:'This device reported that playback failed.',acknowledged:'You confirmed that you heard it.'};
/** On-device voices only, preferring British English. */
export function localVoices(voices:readonly SpeechSynthesisVoice[]):SpeechSynthesisVoice[]{
  const local=voices.filter(v=>v.localService);
  return [...local].sort((a,b)=>Number(b.lang==='en-GB')-Number(a.lang==='en-GB')||Number(b.lang.startsWith('en'))-Number(a.lang.startsWith('en')));
}
export async function sha256Hex(text:string){
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
}
