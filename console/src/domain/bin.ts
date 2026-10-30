/**
 * The bin for ordinary forgets (M05, the owner's rule of 22 October 2026). Shapes mirror
 * GET /desk/memory/bin and POST /desk/memory/bin/{id}/undo (alfred/memory_bin.py,
 * alfred/reviewed_memory.py). An ordinary forget keeps a copy for 30 days so it can be undone;
 * forgetting for good skips the bin. Display logic only: the server checks the owner, the
 * 30 days and every record an undo would put back.
 */
export interface BinLabel{subject?:string|null;predicate?:string|null;value?:string|null;object?:string|null;name?:string|null;kind?:string|null;statements?:number}
export interface BinItem{id:string;kind:'statement'|'entity';subject:string;deleted:number;expires:number;label:BinLabel}
export interface BinView{items:BinItem[];days:number}
export interface UndoResult{kind:'statement'|'entity';subject:string;statements_restored:number;statements_not_restored:number;not_restored:string[]}

export function binLabel(item:BinItem){
  const l=item.label;
  if(item.kind==='entity'){
    const n=l.statements??0;
    return `${l.name??item.subject}${n?` and ${n} statement${n===1?'':'s'}`:''}`;
  }
  return [l.subject??'A record',(l.predicate??'statement').replaceAll('_',' '),l.value??l.object??''].filter(Boolean).join(' · ');
}

/** Whole days left to undo, rounded up, so the last day reads as one day rather than none. */
export function daysLeft(item:BinItem,now:number){return Math.max(0,Math.ceil((item.expires-now)/86400));}

export function undoNotice(item:BinItem,r:UndoResult){return [`Put back ${binLabel(item)}.`,...r.not_restored].join(' ');}

export const BIN_ERRORS:Record<string,string>={
  not_in_bin:'It is no longer in the bin: its 30 days passed, it was undone already, or it was forgotten for good.',
  undo_record_first:'The record this statement is about is not here now. Undo that record first.',
  memory_entity_id_unavailable:'A new record now uses this one’s identifier, so it cannot come back under it.',
  memory_entity_capacity:'Your records are at their limit. Forget one before undoing this.'};

/** What each layer of forgetting does, shown before the owner confirms. */
export const FORGET_LAYERS={
  ordinary:'It goes to the bin for 30 days, where you can undo it. Restoring an older backup brings it back, and ALFRED lists what came back.',
  forGood:'It skips the bin, and restoring any older backup removes it again. Older backups still hold a copy until they are replaced.'};
