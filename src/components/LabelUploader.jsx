import React, { useState, useRef, useCallback } from 'react';

/**
 * Sample Presets for Quick Testing
 */
const SAMPLE_PRESETS = [
  {
    title: "🥔 Spicy Potato Chips",
    badge: "Preservative + Azo Color",
    text: "INGREDIENTS: Potatoes (60%), Refined Palmolein Oil, Iodized Salt, Spices & Condiments, Sugar, Acidity Regulator (INS 330), Preservative (INS 211), Flavour Enhancer (INS 621), Synthetic Food Colour (INS 102, INS 110). Allergen: May contain Milk Solids and Wheat Gluten.",
    productName: "Spicy Masala Potato Chips",
    brandName: "Crunchy Foods Ltd."
  },
  {
    title: "🥤 Sparkling Cola",
    badge: "Caramel + Sweetener",
    text: "INGREDIENTS: Carbonated Water, Sugar, Acidity Regulator (INS 338, INS 330), Colour (INS 150d), Preservative (INS 211), Caffeine (120 mg/kg), Artificial Sweetener (INS 951 Aspartame 500 mg/kg).",
    productName: "Sparkling Energy Cola",
    brandName: "Aura Beverages"
  },
  {
    title: "🍪 Choco Cream Biscuits",
    badge: "Leavener + Soy Allergen",
    text: "INGREDIENTS: Refined Wheat Flour (Maida 55%), Sugar, Edible Vegetable Fat, Invert Sugar Syrup, Cocoa Solids (3%), Raising Agents [INS 500(ii), INS 503(ii)], Emulsifier (INS 322 from Soy), Iodized Salt. Allergen: Contains Wheat, Soy. May contain Peanuts.",
    productName: "Choco Cream Sandwich Biscuits",
    brandName: "NutriBake Bakeries"
  },
  {
    title: "⚠️ Prohibited Substance Test",
    badge: "Potassium Bromate (Banned)",
    text: "INGREDIENTS: Refined Flour, Sugar, Vegetable Margarine, Potassium Bromate (INS 924), Excessive Preservative (INS 211 - 500 ppm), Artificial Colour Tartrazine (INS 102).",
    productName: "Unapproved Bread Formulation",
    brandName: "Non-Compliant Bakery"
  }
];

export default function LabelUploader({
  onAnalyzeImage,
  onAnalyzeText,
  isScanning,
  scanProgress
}) {
  const [activeTab, setActiveTab] = useState('image'); // 'image' | 'text'

  // Image Upload State
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);

  // Text Input State
  const [inputText, setInputText] = useState('');
  const [productName, setProductName] = useState('');
  const [brandName, setBrandName] = useState('');

  const processFile = useCallback((file) => {
    if (!file) return;

    const validTypes = ['image/png', 'image/jpeg', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      alert('Please select a valid image file (PNG, JPG, or WEBP).');
      return;
    }

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

  const handleClearImage = useCallback(() => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setSelectedFile(null);
    setPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (cameraInputRef.current) cameraInputRef.current.value = '';
  }, [previewUrl]);

  const handleTriggerImageAnalysis = useCallback(() => {
    if (selectedFile && onAnalyzeImage) {
      onAnalyzeImage(selectedFile);
    }
  }, [selectedFile, onAnalyzeImage]);

  const handleLoadSampleImage = useCallback(async () => {
    try {
      const response = await fetch('/sample-label.jpg');
      const blob = await response.blob();
      const file = new File([blob], 'sample-fssai-label.jpg', { type: 'image/jpeg' });
      processFile(file);
    } catch (err) {
      console.error('Failed to load sample image:', err);
    }
  }, [processFile]);

  const handleTriggerTextAnalysis = useCallback((e) => {
    e.preventDefault();
    if (!inputText.trim()) {
      alert('Please enter or paste ingredient text first.');
      return;
    }
    if (onAnalyzeText) {
      onAnalyzeText({
        text: inputText,
        productName: productName.trim() || 'Custom Food Product',
        brandName: brandName.trim() || 'Packaging Declaration'
      });
    }
  }, [inputText, productName, brandName, onAnalyzeText]);

  const applyPreset = useCallback((preset) => {
    setInputText(preset.text);
    setProductName(preset.productName);
    setBrandName(preset.brandName);
  }, []);

  return (
    <div className="label-uploader" id="label-uploader-box">
      {/* Tab Switcher */}
      <div className="uploader-tabs">
        <button
          type="button"
          className={`uploader-tab ${activeTab === 'image' ? 'uploader-tab--active' : ''}`}
          onClick={() => setActiveTab('image')}
          disabled={isScanning}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="tab-icon">
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
          </svg>
          Upload Label Image
        </button>

        <button
          type="button"
          className={`uploader-tab ${activeTab === 'text' ? 'uploader-tab--active' : ''}`}
          onClick={() => setActiveTab('text')}
          disabled={isScanning}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="tab-icon">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          </svg>
          Direct Text Input
        </button>
      </div>

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

      {/* TAB 1: Image Upload */}
      {activeTab === 'image' && (
        <>
          {!previewUrl ? (
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
                <strong>Click to upload</strong> or drag and drop food package photo
              </h3>
              <p className="dropzone__hint">Supports PNG, JPG, or WEBP (Max 15MB)</p>

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

                <button
                  type="button"
                  className="btn btn--secondary"
                  onClick={handleLoadSampleImage}
                  disabled={isScanning}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="btn__icon">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z" />
                  </svg>
                  Try Sample Label Photo
                </button>
              </div>
            </div>
          ) : (
            <div className="preview-card">
              <div className="preview-card__image-container">
                <img src={previewUrl} alt="Product label preview" className="preview-card__image" />
                <button
                  type="button"
                  className="preview-card__close-btn"
                  onClick={handleClearImage}
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
                    onClick={handleTriggerImageAnalysis}
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
                        Run OCR & Compliance Audit
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* TAB 2: Text Input */}
      {activeTab === 'text' && (
        <form className="text-input-form" onSubmit={handleTriggerTextAnalysis}>
          <div className="form-meta-row">
            <div className="form-group">
              <label htmlFor="prod-name-input" className="form-label">Product Name (Optional)</label>
              <input
                id="prod-name-input"
                type="text"
                className="form-input"
                placeholder="e.g. Spicy Masala Chips"
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
                disabled={isScanning}
              />
            </div>
            <div className="form-group">
              <label htmlFor="brand-name-input" className="form-label">Brand / Manufacturer (Optional)</label>
              <input
                id="brand-name-input"
                type="text"
                className="form-input"
                placeholder="e.g. Haldiram's / Lay's"
                value={brandName}
                onChange={(e) => setBrandName(e.target.value)}
                disabled={isScanning}
              />
            </div>
          </div>

          <div className="form-group">
            <div className="form-label-row">
              <label htmlFor="text-area-input" className="form-label">Ingredients & Declarations Text</label>
              <span className="form-hint">{inputText.length} characters</span>
            </div>
            <textarea
              id="text-area-input"
              className="form-textarea"
              rows={5}
              placeholder="Paste ingredient list, additives, INS numbers, or package declaration text here...&#10;&#10;e.g. INGREDIENTS: Potatoes, Edible Vegetable Oil, Iodized Salt, Preservative (INS 211), Synthetic Colour (INS 102), Acidity Regulator (INS 330)..."
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              disabled={isScanning}
              required
            />
          </div>

          {/* Preset Buttons */}
          <div className="presets-container">
            <span className="presets-label">Quick Presets:</span>
            <div className="presets-grid">
              {SAMPLE_PRESETS.map((preset, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="preset-chip"
                  onClick={() => applyPreset(preset)}
                  disabled={isScanning}
                  title={preset.text}
                >
                  <span className="preset-chip__title">{preset.title}</span>
                  <span className="preset-chip__badge">{preset.badge}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn btn--outline"
              onClick={() => {
                setInputText('');
                setProductName('');
                setBrandName('');
              }}
              disabled={isScanning || !inputText}
            >
              Clear
            </button>

            <button
              type="submit"
              className="btn btn--primary"
              disabled={isScanning || !inputText.trim()}
            >
              {isScanning ? (
                <>
                  <span className="spinner-border" role="status" />
                  Auditing Ingredients...
                </>
              ) : (
                <>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="btn__icon">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
                  </svg>
                  Check FSSAI Compliance
                </>
              )}
            </button>
          </div>
        </form>
      )}

      {/* Real-time Scanning Progress Bar & Status Steps */}
      {isScanning && (
        <div className="scanning-feedback">
          <div className="scanning-feedback__header">
            <span className="scanning-feedback__status">
              <span className="scanning-feedback__pulse" />
              {scanProgress?.message || 'Processing compliance check...'}
            </span>
            <span className="scanning-feedback__percentage">
              {scanProgress?.progress || 35}%
            </span>
          </div>

          <div className="progress-bar">
            <div
              className="progress-bar__fill"
              style={{ width: `${scanProgress?.progress || 35}%` }}
            />
          </div>

          <div className="scanning-feedback__steps">
            <span className="step-tag">Step {scanProgress?.step || 1} of {scanProgress?.totalSteps || 4}</span>
            <span className="step-hint">FSSAI Regulatory Limits & Additive Cross-Referencing</span>
          </div>
        </div>
      )}
    </div>
  );
}
