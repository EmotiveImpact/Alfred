import {inflateSync} from 'node:zlib';
/** Minimal 8-bit RGB/RGBA PNG reader for screenshot luminance assertions. */
export function luminance(png:Buffer):number {
  let offset=8,width=0,height=0,channels=0;const chunks:Buffer[]=[];
  while(offset<png.length){const length=png.readUInt32BE(offset),type=png.toString('ascii',offset+4,offset+8),data=png.subarray(offset+8,offset+8+length);if(type==='IHDR'){width=data.readUInt32BE(0);height=data.readUInt32BE(4);if(data[8]!==8||![2,6].includes(data[9]))throw new Error('Unsupported screenshot format');channels=data[9]===6?4:3;}if(type==='IDAT')chunks.push(data);offset+=12+length;}
  const raw=inflateSync(Buffer.concat(chunks)),stride=width*channels,output=Buffer.alloc(height*stride);let pos=0,total=0;
  const paeth=(a:number,b:number,c:number)=>{const p=a+b-c,pa=Math.abs(p-a),pb=Math.abs(p-b),pc=Math.abs(p-c);return pa<=pb&&pa<=pc?a:pb<=pc?b:c;};
  for(let y=0;y<height;y++){const filter=raw[pos++];for(let x=0;x<stride;x++){const i=y*stride+x,a=x>=channels?output[i-channels]:0,b=y?output[i-stride]:0,c=y&&x>=channels?output[i-stride-channels]:0;const predict=filter===0?0:filter===1?a:filter===2?b:filter===3?Math.floor((a+b)/2):filter===4?paeth(a,b,c):NaN;if(!Number.isFinite(predict))throw new Error('Unsupported PNG filter');output[i]=(raw[pos++]+predict)&255;}for(let x=0;x<width;x++){const i=y*stride+x*channels;total+=.2126*output[i]+.7152*output[i+1]+.0722*output[i+2];}}
  return total/(width*height);
}
