import React from 'react';

/**
 * IngredientBadge Component
 * =========================
 * Displays color-coded regulatory and safety status badges for ingredients,
 * as well as category tags (Preservative, Synthetic Color, etc.) and INS codes.
 */

export function getStatusDetails(status) {
  const normalized = (status || '').toUpperCase();
  switch (normalized) {
    case 'SAFE':
    case 'WITHIN_LIMIT':
      return {
        label: 'Within Safe Limit',
        emoji: '🟢',
        className: 'badge-status--safe',
        indicatorColor: '#10b981'
      };
    case 'MODERATE':
    case 'CAUTION':
    case 'NEAR_LIMIT':
      return {
        label: 'Close to Limit',
        emoji: '🟡',
        className: 'badge-status--moderate',
        indicatorColor: '#f59e0b'
      };
    case 'EXCEEDS_LIMIT':
    case 'HIGH_RISK':
    case 'PROHIBITED':
    case 'DANGER':
      return {
        label: 'Exceeds Permissible Limit',
        emoji: '🔴',
        className: 'badge-status--danger',
        indicatorColor: '#ef4444'
      };
    default:
      return {
        label: status || 'Unspecified',
        emoji: '⚪',
        className: 'badge-status--unknown',
        indicatorColor: '#94a3b8'
      };
  }
}

export function getCategoryClass(category) {
  const cat = (category || '').toLowerCase();
  if (cat.includes('preservative')) return 'badge-cat--preservative';
  if (cat.includes('color') || cat.includes('dye')) return 'badge-cat--color';
  if (cat.includes('flavor') || cat.includes('msg')) return 'badge-cat--flavor';
  if (cat.includes('acid')) return 'badge-cat--acidity';
  if (cat.includes('antioxidant')) return 'badge-cat--antioxidant';
  if (cat.includes('sweetener')) return 'badge-cat--sweetener';
  return 'badge-cat--default';
}

export default function IngredientBadge({ status, category, insNumber, type = 'status' }) {
  if (type === 'category' && category) {
    return (
      <span className={`badge-category ${getCategoryClass(category)}`}>
        {category}
      </span>
    );
  }

  if (type === 'ins' && insNumber) {
    return (
      <span className="badge-ins">
        <code>{insNumber}</code>
      </span>
    );
  }

  const details = getStatusDetails(status);

  return (
    <span className={`badge-status ${details.className}`} title={details.label}>
      <span className="badge-status__dot" aria-hidden="true">{details.emoji}</span>
      <span className="badge-status__text">{details.label}</span>
    </span>
  );
}
