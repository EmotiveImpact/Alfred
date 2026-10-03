import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import './refinements.css';
import './connected.css';
import './refinement09.css';
const root=document.getElementById('root');
if(!root)throw new Error('ALFRED root element is missing.');
createRoot(root).render(<StrictMode><App/></StrictMode>);
