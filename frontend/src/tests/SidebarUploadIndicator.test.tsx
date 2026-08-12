import { afterEach, describe, expect, it } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "../context/AuthContext";
import { UploadQueueProvider, useUploadQueue } from "../context/UploadQueueContext";
import { SidebarUploadIndicator } from "../components/layout/SidebarUploadIndicator";

afterEach(() => {
  localStorage.clear();
});

/** Adds a queued row on demand, mirroring the queue-provider test harness. */
function Probe() {
  const { addFiles } = useUploadQueue();
  return (
    <button
      onClick={() =>
        addFiles([new File(["x"], "a.pdf", { type: "application/pdf" })])
      }
    >
      add
    </button>
  );
}

const renderIndicator = (collapsed: boolean) =>
  render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route
          path="/"
          element={
            <QueryClientProvider
              client={
                new QueryClient({
                  defaultOptions: { queries: { retry: false } },
                })
              }
            >
              <AuthProvider>
                <UploadQueueProvider>
                  <SidebarUploadIndicator collapsed={collapsed} />
                  <Probe />
                </UploadQueueProvider>
              </AuthProvider>
            </QueryClientProvider>
          }
        />
        <Route path="/documents" element={<div>documents page</div>} />
      </Routes>
    </MemoryRouter>
  );

describe("SidebarUploadIndicator", () => {
  it("renders nothing while the queue is idle", async () => {
    renderIndicator(false);

    expect(screen.queryByText("Uploads")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /in the queue/i })
    ).not.toBeInTheDocument();
    await act(async () => {});
  });

  it("shows the mini strip with the active count once files are queued", async () => {
    renderIndicator(false);

    screen.getByText("add").click();

    expect(await screen.findByText("Uploads")).toBeInTheDocument();
    expect(screen.getByText(/1 · 0%/)).toBeInTheDocument();
    await act(async () => {});
  });

  it("links back to the Documents page where the full queue lives", async () => {
    renderIndicator(false);

    screen.getByText("add").click();
    const indicator = await screen.findByRole("button", {
      name: /in the queue/i,
    });

    indicator.click();
    expect(await screen.findByText("documents page")).toBeInTheDocument();
    await act(async () => {});
  });

  it("renders an icon button with a count badge when collapsed", async () => {
    renderIndicator(true);

    screen.getByText("add").click();

    const button = await screen.findByRole("button", {
      name: /in the queue/i,
    });
    expect(button).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    await act(async () => {});
  });
});
