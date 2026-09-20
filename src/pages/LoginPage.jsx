import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { sendOtp, verifyOtp, updateProfile } from '../services/authApi';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, login, isLoading: authLoading } = useAuth();
  
  // Read mode from query param ?mode=register or default to login
  const queryParams = new URLSearchParams(location.search);
  const initialMode = queryParams.get('mode') === 'register' ? 'register' : 'login';

  const [mode, setMode] = useState(initialMode); // 'login' | 'register'
  const [step, setStep] = useState(1); // 1 = enter details, 2 = verify otp
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [countdown, setCountdown] = useState(0);

  const otpInputs = useRef([]);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      const destination = location.state?.from?.pathname || '/dashboard';
      navigate(destination, { replace: true });
    }
  }, [isAuthenticated, authLoading, navigate, location.state]);

  // Resend OTP countdown timer
  useEffect(() => {
    let timer;
    if (countdown > 0) {
      timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    }
    return () => clearTimeout(timer);
  }, [countdown]);

  // Sync mode changes with url if desired
  const handleSwitchMode = (newMode) => {
    setMode(newMode);
    setError(null);
  };

  const handleSendOtp = async (e) => {
    e.preventDefault();
    const cleanEmail = email.trim().toLowerCase();
    if (!cleanEmail || !cleanEmail.includes('@') || !cleanEmail.includes('.')) {
      setError('Please enter a valid email address.');
      return;
    }
    
    setLoading(true);
    setError(null);
    try {
      await sendOtp(cleanEmail);
      setStep(2);
      setCountdown(60);
      setOtp(['', '', '', '', '', '']);
      setTimeout(() => {
        if (otpInputs.current[0]) otpInputs.current[0].focus();
      }, 50);
    } catch (err) {
      setError(err.message || 'Failed to send OTP. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e, currentOtp = otp.join('')) => {
    if (e) e.preventDefault();
    
    if (currentOtp.length !== 6) {
      setError('Please enter the complete 6-digit OTP.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await verifyOtp(email.trim().toLowerCase(), currentOtp);
      const token = response.data.access_token;
      let userData = response.data.user;

      // If user registered with a display name, persist it to their profile
      if (displayName.trim()) {
        try {
          const profileRes = await updateProfile(token, displayName.trim());
          userData = profileRes.data;
        } catch (profileErr) {
          console.warn("Could not save display name:", profileErr);
        }
      }

      login(token, userData);
      const destination = location.state?.from?.pathname || '/dashboard';
      navigate(destination, { replace: true });
    } catch (err) {
      setError(err.message || 'Invalid or expired OTP. Please try again.');
      setOtp(['', '', '', '', '', '']);
      if (otpInputs.current[0]) {
        otpInputs.current[0].focus();
      }
    } finally {
      setLoading(false);
    }
  };

  const handleOtpChange = (index, value) => {
    if (!/^[0-9]*$/.test(value)) return;
    
    const newOtp = [...otp];
    newOtp[index] = value.slice(-1); // Take single digit
    setOtp(newOtp);

    // Auto-advance to next input
    if (value && index < 5) {
      otpInputs.current[index + 1]?.focus();
    }

    // Auto-submit if all 6 digits are filled
    if (value && index === 5 && newOtp.every(digit => digit !== '')) {
      handleVerifyOtp(null, newOtp.join(''));
    }
  };

  const handleOtpKeyDown = (index, e) => {
    if (e.key === 'Backspace') {
      if (!otp[index] && index > 0) {
        otpInputs.current[index - 1]?.focus();
      }
    } else if (e.key === 'ArrowLeft' && index > 0) {
      otpInputs.current[index - 1]?.focus();
    } else if (e.key === 'ArrowRight' && index < 5) {
      otpInputs.current[index + 1]?.focus();
    }
  };

  const handleOtpPaste = (e) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData('text').trim();
    if (/^\d{6}$/.test(pastedData)) {
      const digits = pastedData.split('');
      setOtp(digits);
      otpInputs.current[5]?.focus();
      handleVerifyOtp(null, pastedData);
    }
  };

  const handleResend = async () => {
    if (countdown > 0 || loading) return;
    
    setLoading(true);
    setError(null);
    try {
      await sendOtp(email.trim().toLowerCase());
      setCountdown(60);
      setOtp(['', '', '', '', '', '']);
      if (otpInputs.current[0]) otpInputs.current[0].focus();
    } catch (err) {
      setError(err.message || 'Failed to resend OTP.');
    } finally {
      setLoading(false);
    }
  };

  if (authLoading) return null;

  return (
    <div className="login-page">
      <div className="login-card">
        {/* Back Link */}
        <div className="login-top-bar">
          <Link to="/" className="back-home-link">
            ← Back to Home
          </Link>
        </div>

        {/* Header */}
        <div className="login-header">
          <div className="login-header__logo">
            <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="2" width="28" height="28" rx="8" fill="url(#nav-grad-login)" />
              <path d="M10 16.5L14 20.5L22 12.5" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              <defs>
                <linearGradient id="nav-grad-login" x1="2" y1="2" x2="30" y2="30">
                  <stop stopColor="#10b981" />
                  <stop offset="1" stopColor="#059669" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h1 className="login-header__title">LabelGuard</h1>
          <p className="login-header__subtitle">
            {step === 1
              ? mode === 'register'
                ? 'Create an account to start compliance auditing'
                : 'Sign in to access the compliance engine'
              : 'Enter the 6-digit verification code sent to your email'}
          </p>
        </div>

        {/* Mode Selector Tabs (Step 1 only) */}
        {step === 1 && (
          <div className="auth-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'login'}
              className={`auth-tab ${mode === 'login' ? 'auth-tab--active' : ''}`}
              onClick={() => handleSwitchMode('login')}
            >
              Sign In
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'register'}
              className={`auth-tab ${mode === 'register' ? 'auth-tab--active' : ''}`}
              onClick={() => handleSwitchMode('register')}
            >
              Create Account
            </button>
          </div>
        )}

        {error && (
          <div className="auth-error" role="alert">
            <svg viewBox="0 0 20 20" fill="currentColor" className="error-icon">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {step === 1 ? (
          <form className="login-form" onSubmit={handleSendOtp}>
            {mode === 'register' && (
              <div className="form-group">
                <label htmlFor="displayName">Full Name / Organization (Optional)</label>
                <input
                  id="displayName"
                  type="text"
                  className="form-input"
                  placeholder="e.g. Inspector Sharma / Quality Lab"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  disabled={loading}
                />
              </div>
            )}

            <div className="form-group">
              <label htmlFor="email">Work or Personal Email</label>
              <input
                id="email"
                type="email"
                className="form-input"
                placeholder="inspector@fssai.gov.in"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={loading}
                required
                autoFocus
              />
            </div>

            <div className="auth-note">
              <svg viewBox="0 0 20 20" fill="currentColor" className="note-icon">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z" clipRule="evenodd" />
              </svg>
              <span>We'll send a one-time passcode. No password needed.</span>
            </div>

            <button 
              type="submit" 
              className="auth-btn auth-btn--primary"
              disabled={loading || !email}
            >
              {loading ? (
                <>
                  <span className="auth-spinner-small"></span>
                  <span>Sending OTP...</span>
                </>
              ) : mode === 'register' ? (
                'Create Account & Send Code'
              ) : (
                'Send Verification Code'
              )}
            </button>
          </form>
        ) : (
          <form className="login-form" onSubmit={handleVerifyOtp}>
            <div className="otp-banner">
              <p className="otp-sent-text">
                Code sent to <strong>{email}</strong>
              </p>
              <span className="otp-expiry-hint">Expires in 5 minutes</span>
            </div>
            
            <div className="otp-inputs" onPaste={handleOtpPaste}>
              {otp.map((digit, index) => (
                <input
                  key={index}
                  ref={(el) => (otpInputs.current[index] = el)}
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={1}
                  className="otp-digit"
                  value={digit}
                  onChange={(e) => handleOtpChange(index, e.target.value)}
                  onKeyDown={(e) => handleOtpKeyDown(index, e)}
                  disabled={loading}
                  aria-label={`Digit ${index + 1}`}
                />
              ))}
            </div>

            <button 
              type="submit" 
              className="auth-btn auth-btn--primary"
              disabled={loading || otp.join('').length !== 6}
            >
              {loading ? (
                <>
                  <span className="auth-spinner-small"></span>
                  <span>Verifying...</span>
                </>
              ) : (
                'Verify & Proceed'
              )}
            </button>

            <div className="login-actions">
              <button 
                type="button" 
                className={`auth-btn auth-btn--link ${countdown > 0 ? 'disabled' : ''}`}
                onClick={handleResend}
                disabled={countdown > 0 || loading}
              >
                {countdown > 0 ? `Resend code in ${countdown}s` : 'Resend code'}
              </button>
              <button 
                type="button" 
                className="auth-btn auth-btn--link"
                onClick={() => {
                  setStep(1);
                  setOtp(['', '', '', '', '', '']);
                }}
                disabled={loading}
              >
                Change Email
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
