import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { Providers } from './app/providers';
import './styles/globals.css';
// React Flow styles (required for CausalGraph)
import '@xyflow/react/dist/style.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Providers>
      <App />
    </Providers>
  </React.StrictMode>
);
