import React from 'react';
import {createRoot} from 'react-dom/client';
import '@fontsource/inter/400.css';import '@fontsource/inter/500.css';import '@fontsource/inter/600.css';import '@fontsource/inter/700.css';
import {App} from './App';import './styles.css';
import {DriverNavigation} from './DriverNavigation';
import {Landing} from './Landing';
import './controlRoom.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode>
 {location.pathname==='/driver'?<DriverNavigation/>:location.pathname==='/welcome'?<Landing/>:<App/>}
</React.StrictMode>);
