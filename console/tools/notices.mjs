import {readFile,writeFile,readdir,access} from 'node:fs/promises';
import {dirname,join} from 'node:path';
const root=process.cwd(),seen=new Set(),items=[];
async function find(name,from){for(let dir=from;;dir=dirname(dir)){const path=join(dir,'node_modules',name);try{await access(join(path,'package.json'));return path;}catch{}if(dirname(dir)===dir)throw new Error(`Missing installed runtime package: ${name}`);}}
async function visit(name,from){const dir=await find(name,from);if(seen.has(dir))return;seen.add(dir);const pkg=JSON.parse(await readFile(join(dir,'package.json'),'utf8'));const files=(await readdir(dir)).filter(x=>/^(licen[sc]e|copying|notice)(\.|$)/i.test(x));let text='';for(const file of files){try{text+=await readFile(join(dir,file),'utf8');text+='\n';}catch{}}
 if(!text&&name==='@react-three/fiber')text=await readFile('tools/licenses/react-three-fiber-MIT.txt','utf8');
 if(!text)throw new Error(`No licence notice found for ${name}@${pkg.version}`);
 items.push(`## ${name}@${pkg.version}\n\nDeclared licence: ${pkg.license??'see notice'}\n\n${text.trim()}\n`);
 for(const dep of Object.keys(pkg.dependencies??{}))await visit(dep,dir);
}
const pkg=JSON.parse(await readFile('package.json','utf8'));for(const name of Object.keys(pkg.dependencies))await visit(name,root);
await writeFile('THIRD_PARTY_NOTICES.md','# ALFRED console / runtime dependency notices\n\nGenerated from the installed runtime dependency tree. Some dependencies may be tree-shaken from the final bundle. The React Three Fiber notice is retained from the official v9.8.1 tag because the npm package omits its licence file.\n\n'+items.sort().join('\n---\n\n'));
console.log(`${items.length} runtime dependency notices retained.`);
