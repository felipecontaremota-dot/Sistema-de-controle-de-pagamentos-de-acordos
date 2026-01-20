import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Cases from './pages/Cases';
import CaseDetail from './pages/CaseDetail';
import Recebimentos from './pages/Recebimentos';
import Import from './pages/Import';
import { Toaster } from './components/ui/sonner';
import './App.css';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));

  useEffect(() => {
    if (token) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
  }, [token]);

  const ProtectedRoute = ({ children }) => {
    if (!token) {
      return <Navigate to="/login" replace />;
    }
    return children;
  };

  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login setToken={setToken} />} />
          <Route
            path="/cases"
            element={
              <ProtectedRoute>
                <Cases token={token} setToken={setToken} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/cases/:id"
            element={
              <ProtectedRoute>
                <CaseDetail token={token} setToken={setToken} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/recebimentos"
            element={
              <ProtectedRoute>
                <Recebimentos token={token} setToken={setToken} />
              </ProtectedRoute>
            }
          />
          <Route
            path="/import"
            element={
              <ProtectedRoute>
                <Import token={token} setToken={setToken} />
              </ProtectedRoute>
            }
          />
          <Route path="/" element={<Navigate to="/cases" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" />
    </div>
  );
}

export default App;
