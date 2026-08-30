import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CodeBlock } from "../components/chat/CodeBlock";
import { CodeInterpreterOutput } from "../components/chat/CodeInterpreterOutput";
import { pyodideManager } from "../lib/pyodide/pyodideManager";

// Mock pyodideManager
vi.mock("../lib/pyodide/pyodideManager", () => {
  return {
    pyodideManager: {
      runCode: vi.fn(),
      terminate: vi.fn(),
    },
  };
});

describe("CodeBlock & CodeInterpreter Component", () => {
  it("renders 'Run in Sandbox' button for python code blocks", () => {
    render(
      <CodeBlock
        code="import pandas as pd\nprint(pd.__version__)"
        language="python"
      />
    );

    expect(screen.getByText("Run in Sandbox")).toBeInTheDocument();
    expect(screen.getByText("wasm sandbox")).toBeInTheDocument();
  });

  it("does not render 'Run in Sandbox' button for standard json or typescript blocks", () => {
    render(
      <CodeBlock
        code='{"name": "test"}'
        language="json"
      />
    );

    expect(screen.queryByText("Run in Sandbox")).not.toBeInTheDocument();
    expect(screen.queryByText("wasm sandbox")).not.toBeInTheDocument();
  });

  it("triggers pyodideManager.runCode when 'Run in Sandbox' is clicked", async () => {
    vi.mocked(pyodideManager.runCode).mockResolvedValueOnce({
      success: true,
      stdout: "2.2.0\n",
      plots: [],
      executionTimeMs: 120,
    });

    render(
      <CodeBlock
        code="import pandas as pd\nprint(pd.__version__)"
        language="python"
      />
    );

    const runBtn = screen.getByText("Run in Sandbox");
    fireEvent.click(runBtn);

    expect(pyodideManager.runCode).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("2.2.0")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("renders CodeInterpreterOutput with console output and generated plots", () => {
    const mockResult = {
      success: true,
      stdout: "Mean sales: 1540.50",
      plots: ["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="],
      executionTimeMs: 250,
    };

    render(
      <CodeInterpreterOutput
        result={mockResult}
        isRunning={false}
      />
    );

    expect(screen.getByText("Console Output")).toBeInTheDocument();
    expect(screen.getByText("Mean sales: 1540.50")).toBeInTheDocument();
    expect(screen.getByText("Generated Visualizations (1)")).toBeInTheDocument();
    expect(screen.getByAltText("Generated plot 1")).toBeInTheDocument();
  });

  it("renders error state when code execution fails", () => {
    const mockErrorResult = {
      success: false,
      stdout: "",
      plots: [],
      executionTimeMs: 50,
      error: "NameError: name 'df' is not defined",
    };

    render(
      <CodeInterpreterOutput
        result={mockErrorResult}
        isRunning={false}
      />
    );

    expect(screen.getByText("Execution Error")).toBeInTheDocument();
    expect(screen.getByText("NameError: name 'df' is not defined")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});
