import {describe,it,expect} from 'vitest';
import {localVoices,spokenText,MAX_SPOKEN,VOICE_LABEL} from '../src/integration/voice';
const voice=(name:string,lang:string,localService:boolean)=>({name,lang,localService,default:false,voiceURI:name}) as SpeechSynthesisVoice;
describe('read aloud (output only)',()=>{
  it('speaks only what the answer shows, and says it is not a generated answer',()=>{
    const text=spokenText('What still needs confirming?',[{title:'Equipment check',excerpt:'## Camera\n[[people/Sample Producer]] confirms the camera\n[[decisions/Camera]]'}]);
    expect(text).toBe('You asked: What still needs confirming? 1 excerpt from your notes. From Equipment check: Camera. Sample Producer confirms the camera. These are your notes read aloud, not a generated answer.');
  });
  it('says plainly when nothing matched and includes reviewed statements',()=>{
    const text=spokenText('Budget?',[],[{subject:{name:'Atlas'},predicate:'status',value:'approved',object:null}]);
    expect(text).toContain('Your reviewed statement: Atlas status approved.');
    expect(text).toContain('Nothing you may read matched this question.');
  });
  it('bounds what is spoken',()=>{
    const long=spokenText('Q?',[{title:'Long',excerpt:'word '.repeat(2000)}]);
    expect(long.length).toBeLessThanOrEqual(MAX_SPOKEN);
    expect(long.endsWith('…')).toBe(true);
  });
  it('never uses an online voice and prefers British English',()=>{
    const chosen=localVoices([voice('Online','en-GB',false),voice('Local US','en-US',true),voice('Local GB','en-GB',true),voice('Local FR','fr-FR',true)]);
    expect(chosen.map(v=>v.name)).toEqual(['Local GB','Local US','Local FR']);
    expect(localVoices([voice('Online','en-GB',false)])).toEqual([]);
  });
  it('keeps played and acknowledged distinct in its wording',()=>{
    expect(VOICE_LABEL.played).toMatch(/not proof that anyone heard it/);
    expect(VOICE_LABEL.acknowledged).toMatch(/You confirmed/);
    expect(VOICE_LABEL.no_local_voice).toMatch(/never uses an online voice/);
  });
});
