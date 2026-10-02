import {useEffect,useRef,useState} from 'react';
import {SpeakerHigh,Stop} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
import {localVoices,sha256Hex,spokenText,VOICE_LABEL,type SpokenEvidence,type SpokenStatement,type VoiceState} from '../integration/voice';
const voicesSoon=(synth:SpeechSynthesis)=>new Promise<SpeechSynthesisVoice[]>(resolve=>{
  const now=synth.getVoices();if(now.length){resolve(now);return;}
  const done=()=>{synth.removeEventListener('voiceschanged',done);resolve(synth.getVoices());};
  synth.addEventListener('voiceschanged',done);setTimeout(done,1000);
});
/** Reads an answer aloud with an on-device voice and records generated, played and acknowledged separately. */
export function ReadAloud({turnId,question,evidence,memory}:{turnId:string;question:string;evidence:readonly SpokenEvidence[];memory:readonly SpokenStatement[]}){
  const c=useConsole(),[state,setState]=useState<VoiceState>('idle'),[text,setText]=useState(''),[error,setError]=useState('');
  const playback=useRef<string|null>(null),reported=useRef(false),stateRef=useRef<VoiceState>('idle');
  const move=(next:VoiceState)=>{stateRef.current=next;setState(next);};
  const report=async(outcome:'ended'|'stopped'|'error')=>{
    if(reported.current||!playback.current)return;reported.current=true;
    try{await c.live.client.post(`/desk/voice/playbacks/${playback.current}/report`,{outcome});}catch{setError('The playback outcome could not be recorded.');}
  };
  useEffect(()=>()=>{if(stateRef.current==='playing'||stateRef.current==='generated'){window.speechSynthesis?.cancel();void report('stopped');}},[]);// eslint-disable-line react-hooks/exhaustive-deps
  const play=async()=>{
    setError('');const synth=window.speechSynthesis;
    const voices=synth?localVoices(await voicesSoon(synth)):[];
    if(!synth||!voices.length){move('no_local_voice');return;}
    const spoken=spokenText(question,evidence,memory);setText(spoken);
    try{
      const made=await c.live.client.post<{id:string}>('/desk/voice/playbacks',{turn_id:turnId,text_sha256:await sha256Hex(spoken),characters:spoken.length,voice_local:true});
      playback.current=made.id;reported.current=false;
    }catch{setError('ALFRED could not record this playback, so nothing was spoken.');return;}
    move('generated');
    const utterance=new SpeechSynthesisUtterance(spoken);utterance.voice=voices[0];utterance.lang=voices[0].lang;
    utterance.onstart=()=>move('playing');
    utterance.onend=()=>{if(stateRef.current==='stopped')return;move('played');void report('ended');};
    utterance.onerror=event=>{if(stateRef.current==='stopped'||event.error==='interrupted'||event.error==='canceled')return;move('failed');void report('error');};
    synth.speak(utterance);
  };
  const stop=()=>{move('stopped');window.speechSynthesis?.cancel();void report('stopped');};
  const acknowledge=async()=>{try{await c.live.client.post(`/desk/voice/playbacks/${playback.current}/acknowledge`,{});move('acknowledged');}catch{setError('The acknowledgement could not be recorded.');}};
  return <div className="read-aloud" aria-label="Read aloud">
    <div className="button-row">
      {state!=='playing'&&state!=='generated'&&<button className="text-button" onClick={()=>void play()}><SpeakerHigh size={14}/>{state==='idle'||state==='no_local_voice'?'Read aloud':'Read again'}</button>}
      {(state==='playing'||state==='generated')&&<button className="text-button" onClick={stop}><Stop size={14}/>Stop</button>}
      {state==='played'&&<button className="text-button" onClick={()=>void acknowledge()}>I heard this</button>}
    </div>
    {state!=='idle'&&<p className={`voice-state ${state}`} role="status">{VOICE_LABEL[state]}</p>}
    {text&&state!=='no_local_voice'&&<details className="spoken-text"><summary>What is spoken</summary><p>{text}</p></details>}
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
  </div>;
}
