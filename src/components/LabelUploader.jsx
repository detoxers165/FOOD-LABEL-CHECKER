import React, { useState, useRef, useCallback } from 'react';

/**
 * LabelUploader Component
 * ======================
 * - Drag-and-drop zone supporting PNG, JPG, WEBP
 * - Mobile camera capture integration via capture="environment"
 * - Instant image preview with file details and clear button
 * - Animated progress indicators for OCR & safety evaluation pipeline
 */
export default function LabelUploader({ onAnalyze, isScanning, scanProgress }) {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);

  const processFile = useCallback((file) => {
    if (!file) return;

    const validTypes = ['image/png', 'image/jpeg', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      alert('Please select a valid image file (PNG, JPG, or WEBP).');
      return;
    }

    // Revoke any previous preview blob URL
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }

    setSelectedFile(file);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
  }, [previewUrl]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  }, [processFile]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }, []);

  const handleClear = useCallback(() => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setSelectedFile(null);
    setPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (cameraInputRef.current) cameraInputRef.current.value = '';
  }, [previewUrl]);

  const handleTriggerAnalysis = useCallback(() => {
    if (selectedFile && onAnalyze) {
      onAnalyze(selectedFile);
    }
  }, [selectedFile, onAnalyze]);

  return (
    <div className="label-uploader" id="label-uploader-box">
      {/* Hidden File Inputs */}
      <input
        type="file"
        ref={fileInputRef}
        accept="image/png,image/jpeg,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => e.target.files?.[0] && processFile(e.target.files[0])}
      />
      <input
        type="file"
        ref={cameraInputRef}
        accept="image/png,image/jpeg,image/webp"
        capture="environment"
        style={{ display: 'none' }}
        onChange={(e) => e.target.files?.[0] && processFile(e.target.files[0])}
      />

      {!previewUrl ? (
        /* Drag & Drop Area */
        <div
          className={`dropzone ${dragOver ? 'dropzone--active' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current?.click()}
        >
          <div className="dropzone__icon-wrapper">
            <svg className="dropzone__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5v-9m0 0l-3.5 3.5M12 7.5l3.5 3.5" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 14.25v3.75a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25v-3.75" />
            </svg>
          </div>

          <h3 className="dropzone__prompt">
            <strong>Click to upload</strong> or drag and drop label photo
          </h3>
          <p className="dropzone__hint">Supports high-res PNG, JPG, or WEBP (Max 15MB)</p>

          <div className="dropzone__quick-actions" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="btn btn--camera"
              onClick={() => cameraInputRef.current?.click()}
              disabled={isScanning}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="btn__icon">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z" />
              </svg>
              Camera Capture
            </button>
          </div>
        </div>
      ) : (
        /* Image Preview Box */
        <div className="preview-card">
          <div className="preview-card__image-container">
            <img src={previewUrl} alt="Product label preview" className="preview-card__image" />
            <button
              type="button"
              className="preview-card__close-btn"
              onClick={handleClear}
              disabled={isScanning}
              title="Remove image"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="preview-card__meta">
            <div className="preview-card__file-details">
              <span className="preview-card__file-name">{selectedFile?.name}</span>
              <span className="preview-card__file-size">
                {(selectedFile.size / 1024).toFixed(1)} KB • {selectedFile.type.replace('image/', '').toUpperCase()}
              </span>
            </div>

            <div className="preview-card__actions">
              <button
                type="button"
                className="btn btn--outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={isScanning}
              >
                Change Image
              </button>
              <button
                type="button"
                className="btn btn--primary"
                onClick={handleTriggerAnalysis}
                disabled={isScanning}
              >
                {isScanning ? (
                  <>
                    <span className="spinner-border" role="status" />
                    Analyzing Label...
                  </>
                ) : (
                  <>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="btn__icon">
                      <circle cx="11" cy="11" r="8" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M11 8v6M8 11h6" />
                    </svg>
                    Analyze Product Label
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Real-time Scanning Progress Bar & Status Steps */}
      {isScanning && (
        <div className="scanning-feedback">
          <div className="scanning-feedback__header">
            <span className="scanning-feedback__status">
              <span className="scanning-feedback__pulse" />
              {scanProgress?.message || 'Processing label analysis...'}
            </span>
            <span className="scanning-feedback__percentage">
              {scanProgress?.progress || 45}%
            </span>
          </div>

          <div className="progress-bar">
            <div
              className="progress-bar__fill"
              style={{ width: `${scanProgress?.progress || 45}%` }}
            />
          </div>

          <div className="scanning-feedback__steps">
            <span className="step-tag">Step {scanProgress?.step || 1} of {scanProgress?.totalSteps || 5}</span>
            <span className="step-hint">FSSAI Regulatory Limits & Additive Cross-Referencing</span>
          </div>
        </div>
      )}
    </div>
  );
}
