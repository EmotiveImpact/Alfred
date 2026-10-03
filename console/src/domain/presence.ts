/** Decorative presentation state, derived only from observable interface activity. */
export type PresenceActivity='present'|'typing'|'retrieving'|'speaking'|'review'|'unavailable';
export const PRESENCE_LABEL:Record<PresenceActivity,string>={present:'Present',typing:'Composing',retrieving:'Retrieving sources',speaking:'Reading aloud',review:'Reviewing proposal',unavailable:'Not connected'};
export function presenceActivity(input:{connected:boolean;ready:boolean;typing:boolean;waiting:boolean;speaking:boolean;reviewing:boolean}):PresenceActivity{
  if(input.connected&&!input.ready)return 'unavailable';
  if(input.speaking)return 'speaking';
  if(input.waiting)return 'retrieving';
  if(input.reviewing)return 'review';
  return input.typing?'typing':'present';
}
/** Sample the exact supplied raster silhouette, without constructing a replacement A. */
export function markSamples(rgba:ArrayLike<number>,width:number,height:number,limit=980){
  const candidates:{x:number;y:number;light:number}[]=[];
  for(let y=0;y<height;y+=3)for(let x=0;x<width;x+=3){
    const i=(y*width+x)*4,light=(rgba[i]+rgba[i+1]+rgba[i+2])/765;
    if(light>.12&&rgba[i+3]>128)candidates.push({x:(x/(width-1)-.5)*2*width/height,y:(.5-y/(height-1))*2,light});
  }
  const count=Math.min(limit,candidates.length);
  return Array.from({length:count},(_,i)=>candidates[Math.floor(i*candidates.length/count)]);
}
