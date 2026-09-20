import React, { useState, useEffect, useCallback } from 'react';
import { Routes, Route, Navigate, Link } from 'react-router-dom';
import LabelUploader from './components/LabelUploader';
import AnalysisDashboard from './components/AnalysisDashboard';
import { scanLabelImage, analyzeLabelText, checkBackendHealth } from './services/api';
import { useAuth } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import LoginPage from './pages/LoginPage';
import LandingPage from './pages/LandingPage';

function MainAppContent() {
  const [backendStatus, setBackendStatus] = useState({ online: false, checking: true });
  const [useMockMode, setUseMockMode] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(null);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [showProfileModal, setShowProfileModal] = useState(false);
  const [editName, setEditName] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileSuccess, setProfileSuccess] = useState(false);
  
  const { user, logout, updateDisplayName } = useAuth();

  // Check backend health on initial load and setup interval poll
  const verifyBackend = useCallback(() => {
    checkBackendHealth().then((status) => {
      setBackendStatus({ online: status.online, checking: false });
      if (status.online) {
        setUseMockMode(false);
      }
    });
  }, []);

  useEffect(() => {
    verifyBackend();
    const interval = setInterval(verifyBackend, 10000);
    return () => clearInterval(interval);
  }, [verifyBackend]);

  useEffect(() => {
    if (user?.display_name) {
      setEditName(user.display_name);
    }
  }, [user]);

  const handleAnalyzeImage = useCallback(async (file) => {
    setIsScanning(true);
    setScanProgress({ step: 1, totalSteps: 4, message: 'Initializing OCR pipeline...', progress: 15 });
    setErrorMessage(null);
    setAnalysisResult(null);

    try {
      const result = await scanLabelImage(file, {
        forceMock: useMockMode,
        onProgress: (progress) => {
          setScanProgress(progress);
        }
      });
      setAnalysisResult(result);
    } catch (err) {
      console.error("Scan error:", err);
      setErrorMessage("Could not complete scan. Falling back to local data.");
    } finally {
      setIsScanning(false);
      setScanProgress(null);
    }
  }, [useMockMode]);

  const handleAnalyzeText = useCallback(async ({ text, productName, brandName, category }) => {
    setIsScanning(true);
    setScanProgress({ step: 1, totalSteps: 3, message: 'Parsing ingredient declarations...', progress: 20 });
    setErrorMessage(null);
    setAnalysisResult(null);

    try {
      const result = await analyzeLabelText(
        { text, productName, brandName, category },
        {
          forceMock: useMockMode,
          onProgress: (progress) => {
            setScanProgress(progress);
          }
        }
      );
      setAnalysisResult(result);
    } catch (err) {
      console.error("Text analysis error:", err);
      setErrorMessage("Could not complete ingredient audit. Please try again.");
    } finally {
      setIsScanning(false);
      setScanProgress(null);
    }
  }, [useMockMode]);

  const handleReset = useCallback(() => {
    setAnalysisResult(null);
    setScanProgress(null);
    setErrorMessage(null);
    setIsScanning(false);
  }, []);

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    if (!editName.trim()) return;
    setSavingProfile(true);
    setProfileSuccess(false);
    try {
      await updateDisplayName(editName.trim());
      setProfileSuccess(true);
      setTimeout(() => {
        setProfileSuccess(false);
        setShowProfileModal(false);
      }, 1200);
    } catch (err) {
      console.error("Profile save error:", err);
    } finally {
      setSavingProfile(false);
    }
  };

  const userInitial = (user?.display_name || user?.email || 'U')[0].toUpperCase();

  return (
    <div className="app-layout">
      {/* 1. Header / Navigation */}
      <header className="navbar">
        <div className="navbar__container">
          <Link to="/" className="navbar__brand" title="Back to Home">
            <div className="navbar__logo">
              <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="2" width="28" height="28" rx="8" fill="url(#nav-grad)" />
                <path d="M10 16.5L14 20.5L22 12.5" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                <defs>
                  <linearGradient id="nav-grad" x1="2" y1="2" x2="30" y2="30">
                    <stop stopColor="#10b981" />
                    <stop offset="1" stopColor="#059669" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <div className="navbar__titles">
              <h1 className="navbar__title">LabelGuard</h1>
              <span className="navbar__subtitle">FSSAI & Legal Metrology Inspector</span>
            </div>
          </Link>

          <div className="navbar__controls">
            {/* Mode Switcher */}
            <button
              type="button"
              className={`mode-badge ${useMockMode ? 'mode-badge--mock' : 'mode-badge--live'}`}
              onClick={() => setUseMockMode(!useMockMode)}
              title="Click to toggle between Live Backend and Simulated Mock Mode"
            >
              <span className="mode-badge__dot" />
              {useMockMode ? 'Mode: Mock / Offline' : 'Mode: Live Backend'}
            </button>

            {/* Backend Connectivity Status */}
            <button
              type="button"
              className="status-pill"
              onClick={verifyBackend}
              title={backendStatus.online ? "Connected to Python Backend (Click to refresh)" : "Python API offline (auto-fallback active). Click to re-check."}
            >
              <span className={`status-pill__indicator ${backendStatus.online ? 'status-pill__indicator--live' : 'status-pill__indicator--sim'}`} />
              <span className="status-pill__label">
                {backendStatus.checking
                  ? 'Checking API...'
                  : backendStatus.online
                    ? 'Backend Live'
                    : 'Backend Offline'}
              </span>
            </button>

            {/* User Account Controls */}
            <div className="navbar__user">
              <button 
                type="button"
                className="user-profile-trigger"
                onClick={() => setShowProfileModal(true)}
                title="View & Edit Account Details"
              >
                <span className="user-avatar">{userInitial}</span>
                <span className="navbar__user-name">{user?.display_name || user?.email?.split('@')[0]}</span>
              </button>

              <button 
                onClick={logout} 
                className="auth-btn auth-btn--outline-light"
                title="Sign out of your session"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* User Profile Modal */}
      {showProfileModal && (
        <div className="modal-backdrop" onClick={() => setShowProfileModal(false)}>
          <div className="profile-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">Account & Inspector Profile</h3>
              <button 
                type="button" 
                className="modal-close-btn"
                onClick={() => setShowProfileModal(false)}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              <div className="user-summary">
                <div className="user-avatar-large">{userInitial}</div>
                <div className="user-summary-text">
                  <span className="user-email-tag">{user?.email}</span>
                  <span className="user-role-badge">
                    <span className="verified-badge">✓</span> Verified Inspector
                  </span>
                </div>
              </div>

              <form onSubmit={handleSaveProfile} className="profile-edit-form">
                <div className="form-group">
                  <label htmlFor="inspectorName">Display Name / Title</label>
                  <input
                    id="inspectorName"
                    type="text"
                    className="form-input"
                    placeholder="e.g. Chief Quality Auditor"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                  />
                </div>

                <div className="profile-details-grid">
                  <div className="detail-item">
                    <span className="detail-item__label">Account ID</span>
                    <span className="detail-item__value font-mono">{user?.id || '—'}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-item__label">Status</span>
                    <span className="detail-item__value">{user?.is_active ? 'Active' : 'Suspended'}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-item__label">Last Login</span>
                    <span className="detail-item__value">
                      {user?.last_login_at ? new Date(user.last_login_at).toLocaleString() : 'Just now'}
                    </span>
                  </div>
                </div>

                {profileSuccess && (
                  <div className="profile-success-msg">
                    ✓ Profile updated successfully!
                  </div>
                )}

                <div className="modal-actions">
                  <button 
                    type="button" 
                    className="auth-btn auth-btn--outline-light"
                    onClick={() => setShowProfileModal(false)}
                  >
                    Close
                  </button>
                  <button 
                    type="submit" 
                    className="auth-btn auth-btn--primary"
                    disabled={savingProfile || !editName.trim()}
                    style={{ width: 'auto' }}
                  >
                    {savingProfile ? 'Saving...' : 'Save Profile'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* 2. Main Content Area */}
      <main className="main-content">
        <div className="main-container">
          {!analysisResult ? (
            <>
              {/* Hero Banner */}
              <div className="hero-section">
                <div className="hero-section__badge">
                  <svg viewBox="0 0 20 20" fill="currentColor" className="badge-svg">
                    <path fillRule="evenodd" d="M10 1.944A11.954 11.954 0 012.166 5C2.056 5.649 2 6.319 2 7c0 5.225 3.34 9.67 8 11.317C14.66 16.67 18 12.225 18 7c0-.682-.057-1.35-.166-2.001A11.954 11.954 0 0110 1.944zM11 14a1 1 0 11-2 0 1 1 0 012 0zm0-7a1 1 0 10-2 0v3a1 1 0 102 0V7z" clipRule="evenodd" />
                  </svg>
                  Automated FSSAI & Legal Metrology Compliance Engine
                </div>
                <h2 className="hero-section__headline">
                  Verify Food Ingredients & <span className="gradient-text">Regulatory Safety</span>
                </h2>
                <p className="hero-section__subheadline">
                  Scan package photos or paste ingredient text directly. Our deep OCR and FSSAI regulation
                  engine checks INS/E-numbers, flags excess preservatives, detects allergens, and audits Legal Metrology declarations.
                </p>
              </div>

              {/* Upload & Scan Component with Image + Text Tabs */}
              <LabelUploader
                onAnalyzeImage={handleAnalyzeImage}
                onAnalyzeText={handleAnalyzeText}
                isScanning={isScanning}
                scanProgress={scanProgress}
              />

              {errorMessage && (
                <div className="error-alert">
                  <span>{errorMessage}</span>
                </div>
              )}

              {/* Information Cards Grid */}
              <div className="info-cards">
                <div className="info-card">
                  <div className="info-card__icon info-card__icon--emerald">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 4.875c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5A1.125 1.125 0 013.75 9.375v-4.5zM3.75 14.625c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5a1.125 1.125 0 01-1.125-1.125v-4.5zM13.5 4.875c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5A1.125 1.125 0 0113.5 9.375v-4.5z" />
                    </svg>
                  </div>
                  <h4 className="info-card__title">PaddleOCR Vision</h4>
                  <p className="info-card__desc">
                    Extracts printed labels, batch numbers, MRP, net weights, and chemical codes directly from packaging photos.
                  </p>
                </div>

                <div className="info-card">
                  <div className="info-card__icon info-card__icon--teal">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
                    </svg>
                  </div>
                  <h4 className="info-card__title">FSSAI Permissible Limits</h4>
                  <p className="info-card__desc">
                    Validates preservatives (INS 211, 202), colors (INS 102, 110), acidity regulators, and bans prohibited additives.
                  </p>
                </div>

                <div className="info-card">
                  <div className="info-card__icon info-card__icon--amber">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                    </svg>
                  </div>
                  <h4 className="info-card__title">Legal Metrology & Allergens</h4>
                  <p className="info-card__desc">
                    Audits mandatory packaging rules (Rule 6, 8, 18) and flags allergens like Gluten, Soy, Peanuts, and Dairy.
                  </p>
                </div>
              </div>
            </>
          ) : (
            /* 3. Analysis Results Dashboard */
            <AnalysisDashboard
              data={analysisResult}
              onReset={handleReset}
            />
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="footer">
        <div className="footer__content">
          <p>© {new Date().getFullYear()} LabelGuard Platform • FSSAI Food Safety & Legal Metrology Inspection Engine</p>
          <p className="footer__subtext">Unified React + Vite Frontend & Python FastAPI Backend</p>
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<LoginPage />} />
      <Route 
        path="/dashboard" 
        element={
          <ProtectedRoute>
            <MainAppContent />
          </ProtectedRoute>
        } 
      />
      <Route 
        path="/app" 
        element={
          <ProtectedRoute>
            <MainAppContent />
          </ProtectedRoute>
        } 
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
