import React from 'react';
import IngredientBadge from './IngredientBadge';

/**
 * AnalysisDashboard Component
 * ===========================
 * Comprehensive breakdown of:
 * 1. Overall Safety Status Banner (SAFE / CAUTION / HIGH RISK)
 * 2. Product Overview Card (product name, brand, count metrics)
 * 3. Additives & Ingredients Table (with INS numbers, categories, limits, & safety status)
 * 4. Regulatory & Health Warnings Callouts
 */

export default function AnalysisDashboard({ data, onReset }) {
  if (!data) return null;

  const {
    productName = "Unidentified Product",
    brandName = "Brand Not Specified",
    overallSafety = "CAUTION",
    scanTimestamp = new Date().toISOString(),
    ingredients = [],
    warnings = []
  } = data;

  const safeCount = ingredients.filter(i => (i.status || '').toUpperCase() === 'SAFE').length;
  const moderateCount = ingredients.filter(i => (i.status || '').toUpperCase() === 'MODERATE' || (i.status || '').toUpperCase() === 'CAUTION').length;
  const riskCount = ingredients.filter(i => (i.status || '').toUpperCase() === 'EXCEEDS_LIMIT' || (i.status || '').toUpperCase() === 'HIGH_RISK').length;

  const getSafetyTheme = (safety) => {
    switch ((safety || '').toUpperCase()) {
      case 'SAFE':
        return {
          title: 'COMPLIANT & SAFE',
          subtitle: 'All detected additives and ingredients reside within permissible FSSAI legal thresholds.',
          className: 'safety-banner--safe',
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z" />
            </svg>
          )
        };
      case 'HIGH_RISK':
      case 'DANGER':
        return {
          title: 'HIGH RISK DETECTED',
          subtitle: 'One or more food ingredients exceed statutory legal safety limits or are prohibited.',
          className: 'safety-banner--danger',
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
          )
        };
      case 'CAUTION':
      default:
        return {
          title: 'CONSUMPTION CAUTION',
          subtitle: 'Elevated preservative or additive concentrations detected. Review safe consumption limits below.',
          className: 'safety-banner--caution',
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
          )
        };
    }
  };

  const safetyTheme = getSafetyTheme(overallSafety);

  return (
    <div className="dashboard" id="analysis-dashboard">
      {/* 1. Overall Safety Status Banner */}
      <section className={`safety-banner ${safetyTheme.className}`}>
        <div className="safety-banner__icon-wrap">
          {safetyTheme.icon}
        </div>
        <div className="safety-banner__text">
          <div className="safety-banner__tag">Overall Safety Audit</div>
          <h2 className="safety-banner__title">{safetyTheme.title}</h2>
          <p className="safety-banner__subtitle">{safetyTheme.subtitle}</p>
        </div>
        <div className="safety-banner__action">
          <button type="button" className="btn btn--outline-light" onClick={onReset}>
            Scan Another
          </button>
        </div>
      </section>

      {/* 2. Product Overview Card & Metric Counters */}
      <section className="overview-card">
        <div className="overview-card__header">
          <div>
            <span className="overview-card__category-hint">Detected Product Identification</span>
            <h3 className="overview-card__title">{productName}</h3>
            <span className="overview-card__brand">Manufacturer / Brand: <strong>{brandName}</strong></span>
          </div>
          <div className="overview-card__timestamp">
            <span>Scanned: {new Date(scanTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
            <small>{new Date(scanTimestamp).toLocaleDateString()}</small>
          </div>
        </div>

        <div className="metrics-grid">
          <div className="metric-box">
            <span className="metric-box__value">{ingredients.length}</span>
            <span className="metric-box__label">Total Ingredients</span>
          </div>
          <div className="metric-box metric-box--safe">
            <span className="metric-box__value">{safeCount}</span>
            <span className="metric-box__label">Within Limit</span>
          </div>
          <div className="metric-box metric-box--moderate">
            <span className="metric-box__value">{moderateCount}</span>
            <span className="metric-box__label">Moderate / Watch</span>
          </div>
          <div className="metric-box metric-box--danger">
            <span className="metric-box__value">{riskCount}</span>
            <span className="metric-box__label">Limit Exceeded</span>
          </div>
        </div>
      </section>

      {/* 3. Additives & Ingredients Breakdown Table */}
      <section className="table-section">
        <div className="section-header">
          <div>
            <h3 className="section-header__title">Additives & Ingredients Breakdown</h3>
            <p className="section-header__desc">
              Cross-referenced with FSSAI regulations, INS/E-number classification, and permissible maximum limits.
            </p>
          </div>
          <span className="section-header__badge">{ingredients.length} Items Evaluated</span>
        </div>

        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Ingredient & Description</th>
                <th>INS / Code</th>
                <th>Category</th>
                <th>Detected Value</th>
                <th>Permissible Limit</th>
                <th>Safety Status</th>
              </tr>
            </thead>
            <tbody>
              {ingredients.map((ing, idx) => (
                <tr key={idx} className={`data-table__row status-row--${(ing.status || '').toLowerCase()}`}>
                  <td className="data-table__cell--name">
                    <strong className="ingredient-title">{ing.name}</strong>
                    {ing.description && (
                      <p className="ingredient-desc">{ing.description}</p>
                    )}
                  </td>
                  <td>
                    <IngredientBadge type="ins" insNumber={ing.insNumber} />
                  </td>
                  <td>
                    <IngredientBadge type="category" category={ing.category} />
                  </td>
                  <td className="font-mono">{ing.detectedValue || 'Present'}</td>
                  <td className="font-mono text-muted">{ing.safeLimit || 'Not Specified'}</td>
                  <td>
                    <IngredientBadge status={ing.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 4. Health & Regulatory Warnings Section */}
      {warnings && warnings.length > 0 && (
        <section className="warnings-section">
          <h3 className="warnings-section__title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="title-icon">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            Health & Regulatory Warnings
          </h3>

          <div className="warnings-grid">
            {warnings.map((warn, index) => (
              <div key={index} className={`warning-card warning-card--${(warn.type || '').toLowerCase()}`}>
                <div className="warning-card__header">
                  <span className="warning-card__tag">{warn.type || 'ADVISORY'}</span>
                </div>
                <p className="warning-card__body">{warn.message}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Reset / Footer Action */}
      <div className="dashboard__footer-actions">
        <button type="button" className="btn btn--primary btn--large" onClick={onReset}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="btn__icon">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
          </svg>
          Scan Another Product Label
        </button>
      </div>
    </div>
  );
}
