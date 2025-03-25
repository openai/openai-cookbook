import React from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import './App.scss';
import { SpeakerPage } from './pages/SpeakerPage';
import { ListenerPage } from './pages/ListenerPage';

function App() {
  return (
    <div data-component="App">

      <Routes>
        <Route path="/speaker" element={<SpeakerPage />} />
        <Route path="/listener" element={<ListenerPage />} />
        {/* Optionally, a default route or home page */}
        <Route path="/" element={<h1>Open /Speaker and /Listener</h1>} />
      </Routes>
    </div>
  );
}

export default App;
