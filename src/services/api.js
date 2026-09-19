/**
 * API Client Connector — Frontend to Backend Service
 * ====================================================
 * Connects the UI to the Python backend (engine.py / label_pipeline.py / FastAPI / Flask).
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
  ]
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

/**
 * Check backend service connectivity.
 * @returns {Promise<{ online: boolean, message: string }>}
 */
export async function checkBackendHealth() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);
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
  // If forceMock is requested or backend is not active, run simulated progress
  if (forceMock) {
    return runSimulatedAnalysis(onProgress);
  }

  try {
    // Attempt real backend call
    const formData = new FormData();
    formData.append('file', imageFile);
    formData.append('image', imageFile); // support both parameter names commonly used in Python backends

    if (onProgress) {
      onProgress({ step: 1, totalSteps: 3, message: "Sending image to backend OCR...", progress: 35 });
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12000); // 12s timeout

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
      onProgress({ step: 3, totalSteps: 3, message: "Parsing backend safety response...", progress: 100 });
    }

    const data = await response.json();
    return {
      ...data,
      scanTimestamp: data.scanTimestamp || new Date().toISOString()
    };
  } catch (error) {
    console.warn("Backend API request failed or not ready. Falling back to simulated analysis pipeline.", error);
    // Graceful fallback to rich simulated analysis
    return runSimulatedAnalysis(onProgress);
  }
}

/**
 * Runs animated simulated OCR and safety checking pipeline
 */
async function runSimulatedAnalysis(onProgress) {
  for (let i = 0; i < SCAN_PROGRESS_STEPS.length; i++) {
    const step = SCAN_PROGRESS_STEPS[i];
    if (onProgress) {
      onProgress({
        step: i + 1,
        totalSteps: SCAN_PROGRESS_STEPS.length,
        message: step.message,
        progress: Math.round(((i + 1) / SCAN_PROGRESS_STEPS.length) * 100)
      });
    }
    await new Promise((res) => setTimeout(res, step.duration));
  }

  return {
    ...MOCK_SCAN_RESPONSE,
    scanTimestamp: new Date().toISOString()
  };
}
