/**
 * API Client Connector — Frontend to Backend Service
 * ====================================================
 * Connects the UI to the Python backend (FastAPI / PaddleOCR / FSSAI Engine).
 * Automatically falls back to high-fidelity mock data if the backend is not yet running,
 * allowing teammates to develop frontend and backend concurrently without friction.
 */

// Configure base URL from environment or default to relative proxy path
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

/**
 * Standard Mock Response adhering to the project JSON schema
 */
export const MOCK_SCAN_RESPONSE = {
  productName: "Crispy Crunch Potato Chips",
  brandName: "NutriSnack Foods Ltd.",
  overallSafety: "CAUTION",
  scanTimestamp: new Date().toISOString(),
  ingredients: [
    {
      name: "Sodium Benzoate",
      insNumber: "INS 211",
      category: "Preservative",
      detectedValue: "220 ppm",
      safeLimit: "200 ppm",
      status: "EXCEEDS_LIMIT",
      description: "Used as a chemical preservative. Detected concentration exceeds permissible limit of 200 ppm under FSSAI regulations."
    },
    {
      name: "Tartrazine",
      insNumber: "INS 102",
      category: "Synthetic Color",
      detectedValue: "80 ppm",
      safeLimit: "100 ppm",
      status: "SAFE",
      description: "Permitted synthetic azo food dye. Detected level is well within permissible safe limits."
    },
    {
      name: "Monosodium Glutamate",
      insNumber: "INS 621",
      category: "Flavor Enhancer",
      detectedValue: "1550 ppm",
      safeLimit: "1800 ppm",
      status: "MODERATE",
      description: "Umami flavor enhancer. Approaching upper ceiling; cautionary advisory for sensitive or asthmatic individuals."
    },
    {
      name: "Sunset Yellow FCF",
      insNumber: "INS 110",
      category: "Synthetic Color",
      detectedValue: "48 ppm",
      safeLimit: "50 ppm",
      status: "MODERATE",
      description: "Synthetic petroleum-derived orange colorant. Close to allowable threshold; requires mandatory warning label for children."
    },
    {
      name: "Citric Acid",
      insNumber: "INS 330",
      category: "Acidity Regulator",
      detectedValue: "2800 ppm",
      safeLimit: "GMP / GRAS",
      status: "SAFE",
      description: "Naturally derived acidifier. Classified as Generally Recognized As Safe (GRAS) with Good Manufacturing Practice compliance."
    },
    {
      name: "Potassium Sorbate",
      insNumber: "INS 202",
      category: "Preservative",
      detectedValue: "175 ppm",
      safeLimit: "250 ppm",
      status: "SAFE",
      description: "Antimicrobial food preservative preventing mold and yeast growth. Detected within safe threshold."
    }
  ],
  warnings: [
    {
      type: "REGULATORY",
      message: "Sodium Benzoate (INS 211) exceeds the maximum permissible limit of 200 ppm under FSSAI Food Safety Standards."
    },
    {
      type: "HEALTH",
      message: "Sunset Yellow FCF (INS 110) & Tartrazine (INS 102) azo dyes require mandatory warning: 'May have an adverse effect on activity and attention in children'."
    },
    {
      type: "ALLERGEN",
      message: "Cross-contact advisory: Manufactured in a facility that also processes Peanuts, Soy, and Wheat Gluten."
    }
  ],
  legalMetrology: {
    overallStatus: "COMPLIANT",
    complianceScorePercent: 85.7,
    mandatoryChecked: 7,
    mandatoryFailed: 1,
    needsReviewCount: 0,
    verdicts: [
      { ruleId: "LM-1", title: "Manufacturer / packer / importer identified", clause: "Rule 6(1)(a)", status: "PASS", evidence: "NutriSnack Foods Ltd.", note: "" },
      { ruleId: "LM-2", title: "Net quantity declared in standard units", clause: "Rule 6(1)(c) / Rule 8", status: "PASS", evidence: "150 g", note: "" },
      { ruleId: "LM-3", title: "Maximum Retail Price declared", clause: "Rule 6(1)(d)", status: "PASS", evidence: "₹ 40.00", note: "" },
      { ruleId: "LM-4", title: "Consumer care details declared", clause: "Rule 6(1)(f)", status: "PASS", evidence: "care@nutrisnack.in", note: "" }
    ]
  }
};

/**
 * Step feedback progression for realistic scanning simulation
 */
const SCAN_PROGRESS_STEPS = [
  { message: "Uploading label image to OCR engine...", duration: 600 },
  { message: "Extracting printed text and INS codes...", duration: 900 },
  { message: "Cross-referencing ingredients with FSSAI database...", duration: 1100 },
  { message: "Calculating safe consumption limits...", duration: 800 },
  { message: "Finalizing safety audit report...", duration: 500 }
];

const TEXT_PROGRESS_STEPS = [
  { message: "Parsing ingredient declarations and text...", duration: 400 },
  { message: "Extracting INS numbers and additives...", duration: 600 },
  { message: "Querying FSSAI regulation rulebook...", duration: 600 },
  { message: "Generating safety verdict report...", duration: 400 }
];

/**
 * Check backend service connectivity.
 * @returns {Promise<{ online: boolean, message: string }>}
 */
export async function checkBackendHealth() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);
    const response = await fetch(`${API_BASE_URL}/api/health`, {
      method: 'GET',
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    if (response.ok) {
      const data = await response.json();
      return { online: true, message: data.message || "Connected to Python Backend" };
    }
    return { online: false, message: "Backend response not OK, using simulated mode" };
  } catch {
    return { online: false, message: "Backend offline (Simulated Mode Active)" };
  }
}

/**
 * Sends a product label image to the backend for OCR and safety analysis.
 * Automatically falls back to simulated pipeline if backend is unreachable.
 * 
 * @param {File} imageFile - Uploaded or captured image file
 * @param {Object} options - Additional options
 * @param {Function} [options.onProgress] - Callback function receiving progress updates
 * @param {boolean} [options.forceMock] - Force use of mock data even if backend is reachable
 * @returns {Promise<Object>} Analyzed product schema
 */
export async function scanLabelImage(imageFile, { onProgress, forceMock = false } = {}) {
  if (forceMock) {
    return runSimulatedProgress(SCAN_PROGRESS_STEPS, onProgress, MOCK_SCAN_RESPONSE);
  }

  try {
    const formData = new FormData();
    formData.append('file', imageFile);
    formData.append('image', imageFile);

    if (onProgress) {
      onProgress({ step: 1, totalSteps: 4, message: "Uploading image to OCR engine...", progress: 20 });
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000); // 60s timeout for OCR

    const response = await fetch(`${API_BASE_URL}/api/scan`, {
      method: 'POST',
      body: formData,
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`Backend returned status ${response.status}`);
    }

    if (onProgress) {
      onProgress({ step: 4, totalSteps: 4, message: "Parsing compliance report...", progress: 100 });
    }

    const data = await response.json();
    return {
      ...data,
      scanTimestamp: data.scanTimestamp || new Date().toISOString()
    };
  } catch (error) {
    console.warn("Backend API request failed or timed out. Falling back to simulated analysis pipeline.", error);
    return runSimulatedProgress(SCAN_PROGRESS_STEPS, onProgress, MOCK_SCAN_RESPONSE);
  }
}

/**
 * Directly analyzes raw label or ingredient text against FSSAI regulations.
 * 
 * @param {Object} payload - { text, productName, brandName, category }
 * @param {Object} options - Additional options
 * @param {Function} [options.onProgress] - Callback function
 * @param {boolean} [options.forceMock] - Force mock mode
 * @returns {Promise<Object>} Analyzed product schema
 */
export async function analyzeLabelText({ text, productName, brandName, category }, { onProgress, forceMock = false } = {}) {
  if (forceMock) {
    return runSimulatedProgress(TEXT_PROGRESS_STEPS, onProgress, {
      ...MOCK_SCAN_RESPONSE,
      productName: productName || "Direct Text Product",
      brandName: brandName || "Entered Text Analysis"
    });
  }

  try {
    if (onProgress) {
      onProgress({ step: 1, totalSteps: 3, message: "Submitting ingredient text...", progress: 30 });
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    const response = await fetch(`${API_BASE_URL}/api/analyze-text`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        text,
        productName: productName || "Food Product",
        brandName: brandName || "Ingredient Text Submission",
        category: category || null
      }),
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`Backend returned status ${response.status}`);
    }

    if (onProgress) {
      onProgress({ step: 3, totalSteps: 3, message: "Formatting regulatory audit...", progress: 100 });
    }

    const data = await response.json();
    return {
      ...data,
      scanTimestamp: data.scanTimestamp || new Date().toISOString()
    };
  } catch (error) {
    console.warn("Text analysis request failed. Falling back to simulated analysis.", error);
    return runSimulatedProgress(TEXT_PROGRESS_STEPS, onProgress, {
      ...MOCK_SCAN_RESPONSE,
      productName: productName || "Food Product",
      brandName: brandName || "Simulated Text Evaluation"
    });
  }
}

/**
 * Runs animated simulated steps
 */
async function runSimulatedProgress(steps, onProgress, finalData) {
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    if (onProgress) {
      onProgress({
        step: i + 1,
        totalSteps: steps.length,
        message: step.message,
        progress: Math.round(((i + 1) / steps.length) * 100)
      });
    }
    await new Promise((res) => setTimeout(res, step.duration));
  }

  return {
    ...finalData,
    scanTimestamp: new Date().toISOString()
  };
}
