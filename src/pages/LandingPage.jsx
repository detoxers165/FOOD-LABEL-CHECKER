import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function LandingPage() {
  const { isAuthenticated, user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="landing-page">
      {/* Navigation Bar */}
      <header className="landing-nav">
        <div className="landing-nav__container">
          <Link to="/" className="landing-nav__brand">
            <div className="navbar__logo">
              <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="2" width="28" height="28" rx="8" fill="url(#landing-nav-grad)" />
                <path d="M10 16.5L14 20.5L22 12.5" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                <defs>
                  <linearGradient id="landing-nav-grad" x1="2" y1="2" x2="30" y2="30">
                    <stop stopColor="#10b981" />
                    <stop offset="1" stopColor="#059669" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <div className="landing-nav__titles">
              <span className="landing-nav__title">LabelGuard</span>
              <span className="landing-nav__tag">FSSAI & Metrology Inspector</span>
            </div>
          </Link>

          <nav className="landing-nav__links">
            <a href="#features" className="landing-nav__link">Capabilities</a>
            <a href="#how-it-works" className="landing-nav__link">How It Works</a>
            <a href="#regulations" className="landing-nav__link">Regulations</a>
          </nav>

          <div className="landing-nav__actions">
            {isAuthenticated ? (
              <div className="landing-nav__user-menu">
                <span className="landing-nav__user-badge">
                  <span className="status-dot"></span>
                  {user?.display_name || user?.email}
                </span>
                <button
                  onClick={() => navigate('/dashboard')}
                  className="auth-btn auth-btn--primary landing-nav__cta"
                >
                  Go to Dashboard →
                </button>
                <button
                  onClick={logout}
                  className="auth-btn auth-btn--outline-light"
                  style={{ width: 'auto' }}
                >
                  Logout
                </button>
              </div>
            ) : (
              <div className="landing-nav__auth-buttons">
                <button
                  onClick={() => navigate('/login')}
                  className="landing-nav__login-btn"
                >
                  Sign In
                </button>
                <button
                  onClick={() => navigate('/login?mode=register')}
                  className="auth-btn auth-btn--primary landing-nav__cta"
                >
                  Create Account
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="landing-hero">
        <div className="landing-hero__badge">
          <span className="pulse-dot"></span>
          FSSAI (Food Safety & Standards) & Legal Metrology Compliance Engine
        </div>

        <h1 className="landing-hero__title">
          Verify Food Labels & <br />
          <span className="gradient-text">Regulatory Safety Instantly</span>
        </h1>

        <p className="landing-hero__subtitle">
          Next-generation deep OCR vision and regulatory intelligence. Scan food packaging or paste ingredient declarations to detect excess preservatives, audit INS/E-numbers, verify mandatory Legal Metrology declarations, and flag allergens.
        </p>

        <div className="landing-hero__actions">
          {isAuthenticated ? (
            <button
              onClick={() => navigate('/dashboard')}
              className="hero-btn hero-btn--primary"
            >
              Open Inspector Dashboard →
            </button>
          ) : (
            <>
              <button
                onClick={() => navigate('/login?mode=register')}
                className="hero-btn hero-btn--primary"
              >
                Start Free Inspection
              </button>
              <button
                onClick={() => navigate('/login')}
                className="hero-btn hero-btn--secondary"
              >
                Sign In with Email OTP
              </button>
            </>
          )}
        </div>

        {/* Highlight Stats Strip */}
        <div className="landing-stats">
          <div className="stat-card">
            <span className="stat-card__number">INS 100–1521</span>
            <span className="stat-card__label">Additives & E-numbers Audited</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__number">FSSAI 2020</span>
            <span className="stat-card__label">Labeling & Display Standards</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__number">PCR 2011</span>
            <span className="stat-card__label">Legal Metrology Declarations</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__number">PaddleOCR</span>
            <span className="stat-card__label">Deep Package Text Recognition</span>
          </div>
        </div>
      </section>

      {/* Feature Section */}
      <section id="features" className="landing-section">
        <div className="landing-section__header">
          <span className="section-eyebrow">Comprehensive Inspection Engine</span>
          <h2 className="section-title">Built for Quality Auditors & Consumers</h2>
          <p className="section-subtitle">
            Combines optical text recognition with automated compliance rules to deliver instant regulatory verdicts.
          </p>
        </div>

        <div className="features-grid">
          <div className="feature-card">
            <div className="feature-card__icon feature-card__icon--emerald">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 4.875c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5A1.125 1.125 0 013.75 9.375v-4.5zM3.75 14.625c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5a1.125 1.125 0 01-1.125-1.125v-4.5zM13.5 4.875c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5A1.125 1.125 0 0113.5 9.375v-4.5z" />
              </svg>
            </div>
            <h3 className="feature-card__title">Deep OCR Vision</h3>
            <p className="feature-card__desc">
              High-accuracy layout analysis and text detection for curved packages, small print nutrition tables, manufacturer details, and MRP labels.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-card__icon feature-card__icon--teal">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
              </svg>
            </div>
            <h3 className="feature-card__title">FSSAI Permissible Limits</h3>
            <p className="feature-card__desc">
              Automatically identifies chemical preservatives (INS 211, 202), synthetic colorants (Tartrazine, Sunset Yellow), and flags concentration violations.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-card__icon feature-card__icon--amber">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
            </div>
            <h3 className="feature-card__title">Legal Metrology Audit</h3>
            <p className="feature-card__desc">
              Checks mandatory declarations under Rule 6(1): Net weight, batch code, expiry date, MRP (inclusive of all taxes), and consumer care contacts.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-card__icon feature-card__icon--rose">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
              </svg>
            </div>
            <h3 className="feature-card__title">Allergen Safety Flagging</h3>
            <p className="feature-card__desc">
              Instantly detects allergen ingredients like gluten, peanuts, tree nuts, dairy, soy, and sulfites with cautionary advisories.
            </p>
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section id="how-it-works" className="landing-section landing-section--alt">
        <div className="landing-section__header">
          <span className="section-eyebrow">Seamless Workflow</span>
          <h2 className="section-title">How LabelGuard Works</h2>
          <p className="section-subtitle">Three straightforward steps from packaging photo to complete compliance verdict.</p>
        </div>

        <div className="steps-container">
          <div className="step-box">
            <div className="step-box__badge">1</div>
            <h4 className="step-box__title">Upload or Paste</h4>
            <p className="step-box__desc">
              Upload any food package label image or paste ingredient declaration text directly into the inspector.
            </p>
          </div>

          <div className="step-arrow">→</div>

          <div className="step-box">
            <div className="step-box__badge">2</div>
            <h4 className="step-box__title">Automated Analysis</h4>
            <p className="step-box__desc">
              PaddleOCR extracts all textual tokens; our regulation rulebook evaluates INS additives and statutory declarations.
            </p>
          </div>

          <div className="step-arrow">→</div>

          <div className="step-box">
            <div className="step-box__badge">3</div>
            <h4 className="step-box__title">Compliance Report</h4>
            <p className="step-box__desc">
              Get an overall safety verdict (SAFE, CAUTION, NON-COMPLIANT), per-ingredient limit charts, and metrology audit.
            </p>
          </div>
        </div>
      </section>

      {/* Regulations Covered Section */}
      <section id="regulations" className="landing-section">
        <div className="landing-section__header">
          <span className="section-eyebrow">Regulatory Framework</span>
          <h2 className="section-title">Standardized Indian Food Safety Regulations</h2>
        </div>

        <div className="regulations-grid">
          <div className="regulation-card">
            <div className="regulation-card__tag">FSSAI 2020</div>
            <h4 className="regulation-card__title">Food Safety and Standards (Labelling and Display) Regulations</h4>
            <p className="regulation-card__desc">
              Mandatory nutritional declaration per 100g/serving, veg/non-veg logo positioning, allergen declaration, and front-of-pack labeling standards.
            </p>
          </div>

          <div className="regulation-card">
            <div className="regulation-card__tag">LM PCR 2011</div>
            <h4 className="regulation-card__title">Legal Metrology (Packaged Commodities) Rules</h4>
            <p className="regulation-card__desc">
              Rule 6(1) declarations: Name and address of manufacturer/packer, country of origin, net quantity, month/year of manufacture, and maximum retail price.
            </p>
          </div>

          <div className="regulation-card">
            <div className="regulation-card__tag">FSSAI 2011</div>
            <h4 className="regulation-card__title">Food Additives & Contaminants Regulations</h4>
            <p className="regulation-card__desc">
              Comprehensive INS schedules specifying maximum permitted concentrations of preservatives, antioxidants, emulsifiers, artificial sweeteners, and colorants.
            </p>
          </div>
        </div>
      </section>

      {/* CTA Footer Banner */}
      <section className="landing-cta">
        <h2 className="landing-cta__title">Ready to audit food packaging compliance?</h2>
        <p className="landing-cta__subtitle">
          Sign in instantly with your email to start analyzing food labels.
        </p>
        <div className="landing-cta__actions">
          {isAuthenticated ? (
            <button
              onClick={() => navigate('/dashboard')}
              className="hero-btn hero-btn--primary"
            >
              Go to Dashboard →
            </button>
          ) : (
            <button
              onClick={() => navigate('/login?mode=register')}
              className="hero-btn hero-btn--primary"
            >
              Get Started Now — It's Free
            </button>
          )}
        </div>
      </section>

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
