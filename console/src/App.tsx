import {AnimatePresence,MotionConfig,motion} from 'motion/react';
import {Check} from '@phosphor-icons/react';
import {ConsoleProvider,useConsole} from './state/ConsoleProvider';
import {NavigationRail} from './components/NavigationRail';
import {WorkspaceHeader} from './components/WorkspaceHeader';
import {KnowledgeStage} from './components/KnowledgeStage';
import {ExecutivePanel} from './components/ExecutivePanel';
import {CommandBar} from './components/CommandBar';
import {RecordInspector} from './components/RecordInspector';
import {ConsoleDialogs} from './components/ConsoleDialogs';
import './styles.css';
function ConsoleShell(){const{state,reduced,notice}=useConsole();return <MotionConfig reducedMotion={reduced?'always':'user'}><div className={`console ${state.focus?'focus-mode':''}`}><a className="skip-link" href="#workspace">Skip to workspace</a><NavigationRail/><WorkspaceHeader/><main id="workspace" className="workspace"><KnowledgeStage/><CommandBar/></main><ExecutivePanel/><RecordInspector/><ConsoleDialogs/><AnimatePresence>{notice&&<motion.div className="toast" role="status" initial={{opacity:0,y:10}} animate={{opacity:1,y:0}} exit={{opacity:0}}><Check size={17}/>{notice}</motion.div>}</AnimatePresence></div></MotionConfig>;}
export default function App(){return <ConsoleProvider><ConsoleShell/></ConsoleProvider>;}
