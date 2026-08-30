/* eslint-disable no-restricted-globals */
/* eslint-disable @typescript-eslint/no-explicit-any */
// Pyodide Web Worker for Sandboxed In-Browser Python Execution

export interface RunRequest {
  id: string;
  type: "RUN";
  code: string;
  files?: Record<string, string>; // filename -> content
}

export interface WorkerResponse {
  id: string;
  type: "RUN_RESULT" | "STATUS_UPDATE";
  success?: boolean;
  status?: string;
  stdout?: string;
  stderr?: string;
  plots?: string[]; // base64 data URLs
  executionTimeMs?: number;
  error?: string;
}

let pyodideInstance: any = null;
let isInitializing = false;

const PYODIDE_CDN_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js";

async function getPyodide(): Promise<any> {
  if (pyodideInstance) {
    return pyodideInstance;
  }

  if (isInitializing) {
    while (isInitializing) {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    return pyodideInstance;
  }

  isInitializing = true;
  try {
    // Import Pyodide script inside worker
    if (typeof (self as any).loadPyodide === "undefined") {
      (self as any).importScripts(PYODIDE_CDN_URL);
    }

    pyodideInstance = await (self as any).loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/",
    });

    // Pre-initialize micropip
    await pyodideInstance.loadPackage("micropip");

    // Standard Python sandbox bootstrapping: setup stdout/stderr capture and matplotlib hooks
    const setupScript = `
import sys
import io
import base64

# Setup standard output captures
class OutputRedirector:
    def __init__(self):
        self.stdout_buf = io.StringIO()
        self.stderr_buf = io.StringIO()

    def start(self):
        self.stdout_buf = io.StringIO()
        self.stderr_buf = io.StringIO()
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = self.stdout_buf
        sys.stderr = self.stderr_buf

    def stop(self):
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr
        return self.stdout_buf.getvalue(), self.stderr_buf.getvalue()

_redirector = OutputRedirector()
`;
    pyodideInstance.runPython(setupScript);
    return pyodideInstance;
  } finally {
    isInitializing = false;
  }
}

// Inspect imports in code and load required packages dynamically
async function loadRequiredPackages(pyodide: any, code: string): Promise<void> {
  const packageMap: Record<string, string> = {
    pandas: "pandas",
    pd: "pandas",
    numpy: "numpy",
    np: "numpy",
    matplotlib: "matplotlib",
    plt: "matplotlib",
    scipy: "scipy",
    statsmodels: "statsmodels",
    sympy: "sympy",
    seaborn: "seaborn",
    sns: "seaborn",
  };

  const toLoad = new Set<string>();
  for (const [key, pkg] of Object.entries(packageMap)) {
    const importRegex = new RegExp(`\\b(import\\s+${key}|from\\s+${key})\\b`, "i");
    if (importRegex.test(code)) {
      toLoad.add(pkg);
    }
  }

  if (toLoad.size > 0) {
    await pyodide.loadPackage(Array.from(toLoad));
  }
}

self.onmessage = async (e: MessageEvent<RunRequest>) => {
  const req = e.data;
  if (!req || req.type !== "RUN") return;

  const startTime = performance.now();

  try {
    self.postMessage({
      id: req.id,
      type: "STATUS_UPDATE",
      status: "Initializing Python WebAssembly runtime...",
    } as WorkerResponse);

    const pyodide = await getPyodide();

    self.postMessage({
      id: req.id,
      type: "STATUS_UPDATE",
      status: "Loading required data packages...",
    } as WorkerResponse);

    await loadRequiredPackages(pyodide, req.code);

    // Mount virtual files into Pyodide filesystem if any
    if (req.files) {
      for (const [filename, content] of Object.entries(req.files)) {
        pyodide.FS.writeFile(filename, content);
      }
    }

    self.postMessage({
      id: req.id,
      type: "STATUS_UPDATE",
      status: "Executing code in sandbox...",
    } as WorkerResponse);

    // Configure matplotlib backend if matplotlib is loaded
    const wrapperScript = `
_redirector.start()
_captured_plots = []

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    _has_mpl = True
except ImportError:
    _has_mpl = False

_exec_error = None
try:
    exec(${JSON.stringify(req.code)}, globals())
except Exception as _e:
    _exec_error = _e

if _has_mpl:
    import matplotlib.pyplot as plt
    fignums = plt.get_fignums()
    for fignum in fignums:
        fig = plt.figure(fignum)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=130)
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('ascii')
        _captured_plots.append(f"data:image/png;base64,{img_b64}")
    plt.close('all')

_stdout, _stderr = _redirector.stop()
if _exec_error is not None:
    raise _exec_error
`;

    pyodide.runPython(wrapperScript);

    const stdout = pyodide.globals.get("_stdout") || "";
    const stderr = pyodide.globals.get("_stderr") || "";
    const pyPlots = pyodide.globals.get("_captured_plots");
    const plots: string[] = pyPlots ? pyPlots.toJs() : [];

    const elapsedMs = performance.now() - startTime;

    self.postMessage({
      id: req.id,
      type: "RUN_RESULT",
      success: true,
      stdout,
      stderr,
      plots,
      executionTimeMs: elapsedMs,
    } as WorkerResponse);
  } catch (err: unknown) {
    const elapsedMs = performance.now() - startTime;
    // Extract stdout if partially written
    let stdout = "";
    try {
      if (pyodideInstance && pyodideInstance.globals) {
        stdout = pyodideInstance.globals.get("_stdout") || "";
      }
    } catch {
      // ignore
    }

    const errorMessage = err instanceof Error ? err.message : String(err);

    self.postMessage({
      id: req.id,
      type: "RUN_RESULT",
      success: false,
      stdout,
      error: errorMessage,
      executionTimeMs: elapsedMs,
    } as WorkerResponse);
  }
};
