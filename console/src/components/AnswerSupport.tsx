import {ListChecks} from '@phosphor-icons/react';
import {describeSupport,type SupportReport} from '../integration/answerSupport';
/** What supports this answer: word coverage and counts from the server. Not truth, not completeness. */
export function AnswerSupport({report}:{report:SupportReport|undefined}){
  if(!report)return null;
  const d=describeSupport(report);
  return <section className={`answer-support ${d.tone}`} aria-label="What supports this answer">
    <h3><ListChecks size={14}/>What supports this answer</h3>
    <p>{d.headline}</p>
    <ul>{d.facts.map(f=><li key={f}>{f}</li>)}</ul>
    <small>{report.limits}</small></section>;
}
