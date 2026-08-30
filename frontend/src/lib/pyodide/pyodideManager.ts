import { RunRequest, WorkerResponse } from "../../workers/pyodide.worker";

export interface ExecutionResult {
  success: boolean;
  stdout: string;
  stderr?: string;
  plots: string[];
  executionTimeMs: number;
  error?: string;
}

export type StatusCallback = (status: string) => void;

class PyodideManager {
  private worker: Worker | null = null;
  private pendingRequests = new Map<
    string,
    {
      resolve: (res: ExecutionResult) => void;
      reject: (err: unknown) => void;
      onStatus?: StatusCallback;
      timer: NodeJS.Timeout;
    }
  >();

  private getWorker(): Worker {
    if (!this.worker) {
      // Initialize web worker via Vite's standard module worker syntax
      this.worker = new Worker(
        new URL("../../workers/pyodide.worker.ts", import.meta.url),
        { type: "module" }
      );

      this.worker.onmessage = (e: MessageEvent<WorkerResponse>) => {
        const msg = e.data;
        if (!msg || !msg.id) return;

        const pending = this.pendingRequests.get(msg.id);
        if (!pending) return;

        if (msg.type === "STATUS_UPDATE" && msg.status && pending.onStatus) {
          pending.onStatus(msg.status);
          return;
        }

        if (msg.type === "RUN_RESULT") {
          clearTimeout(pending.timer);
          this.pendingRequests.delete(msg.id);

          pending.resolve({
            success: !!msg.success,
            stdout: msg.stdout || "",
            stderr: msg.stderr,
            plots: msg.plots || [],
            executionTimeMs: msg.executionTimeMs || 0,
            error: msg.error,
          });
        }
      };

      this.worker.onerror = (err) => {
        console.error("Pyodide Worker Error:", err);
        // Fail all pending
        for (const [id, pending] of this.pendingRequests.entries()) {
          clearTimeout(pending.timer);
          pending.reject(new Error("Pyodide Worker crashed or encountered an error."));
          this.pendingRequests.delete(id);
        }
        this.worker?.terminate();
        this.worker = null;
      };
    }

    return this.worker;
  }

  public async runCode(
    code: string,
    files?: Record<string, string>,
    onStatus?: StatusCallback,
    timeoutMs = 45000
  ): Promise<ExecutionResult> {
    const worker = this.getWorker();
    const id = `exec_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;

    return new Promise<ExecutionResult>((resolve, reject) => {
      const timer = setTimeout(() => {
        if (this.pendingRequests.has(id)) {
          this.pendingRequests.delete(id);
          // Terminate and recreate worker to stop runaway infinite loop
          this.terminate();
          resolve({
            success: false,
            stdout: "",
            plots: [],
            executionTimeMs: timeoutMs,
            error: `Execution timed out after ${timeoutMs / 1000}s. Sandbox was safely reset.`,
          });
        }
      }, timeoutMs);

      this.pendingRequests.set(id, { resolve, reject, onStatus, timer });

      const request: RunRequest = {
        id,
        type: "RUN",
        code,
        files,
      };

      worker.postMessage(request);
    });
  }

  public terminate(): void {
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
    }
  }
}

export const pyodideManager = new PyodideManager();
