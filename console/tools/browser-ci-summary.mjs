import {readFile,appendFile} from 'node:fs/promises';
const output=process.env.GITHUB_STEP_SUMMARY;
const lines=['## Console browser acceptance',`Tested commit: ${process.env.GITHUB_SHA??'local checkout'}`,''];
try{
  const report=JSON.parse(await readFile('evidence/browser-results.json','utf8'));
  const stats=report.stats;
  lines.push(`Passed: ${stats.expected}; failed: ${stats.unexpected}; skipped: ${stats.skipped}; flaky: ${stats.flaky}.`,'');
  function visit(suite){
    for(const spec of suite.specs??[])if(!spec.ok){
      lines.push(`### ${spec.title}`,`${spec.file}:${spec.line}`,'');
      for(const test of spec.tests??[])for(const result of test.results??[])for(const error of result.errors??[]){
        const message=(error.message??'No message').replace(/\u001b\[[0-9;]*m/g,'').replaceAll('```','\u0060 \u0060 \u0060').slice(0,4000);
        lines.push('```text',message,'```','');
      }
    }
    for(const child of suite.suites??[])visit(child);
  }
  for(const suite of report.suites??[])visit(suite);
}catch{
  lines.push('No browser JSON report was produced. Inspect the separately named build, browser-tool and acceptance steps.');
}
const summary=lines.join('\n')+'\n';
if(output)await appendFile(output,summary);else process.stdout.write(summary);
