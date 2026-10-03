import {SurfaceTrace} from './SurfaceMotion';
import {useLayoutEffect,useRef,type ReactNode} from 'react';
import {X} from '@phosphor-icons/react';
export function Dialog({title,subtitle,children,onClose,wide=false}:{title:string;subtitle?:string;children:ReactNode;onClose:()=>void;wide?:boolean}){
 const ref=useRef<HTMLDialogElement>(null),previous=useRef<HTMLElement|null>(null);
 useLayoutEffect(()=>{previous.current=document.activeElement as HTMLElement;ref.current?.showModal();return()=>{ref.current?.close();previous.current?.focus();};},[]);
 return <dialog ref={ref} className={`dialog ${wide?'dialog-wide':''}`} aria-labelledby="dialog-title" onCancel={e=>{e.preventDefault();onClose();}} onClick={e=>{if(e.target===ref.current)onClose();}}><SurfaceTrace/><div className="dialog-content"><header className="dialog-header"><div><p className="eyebrow">{subtitle??'ALFRED / DESIGN BUILD'}</p><h2 id="dialog-title">{title}</h2></div><button className="icon-button" aria-label="Close panel" onClick={onClose}><X size={20}/></button></header>{children}</div></dialog>;
}
