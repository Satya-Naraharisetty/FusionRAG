import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownRenderer } from "../components/chat/MarkdownRenderer";

describe("MarkdownRenderer with KaTeX", () => {
  it("renders standard markdown text", () => {
    const { getByText } = render(<MarkdownRenderer content="Hello world" />);
    expect(getByText("Hello world")).toBeInTheDocument();
  });

  it("renders inline math with katex classes", () => {
    const { container } = render(<MarkdownRenderer content="Here is inline math: $E = mc^2$" />);
    const katexEl = container.querySelector(".katex");
    expect(katexEl).toBeInTheDocument();
  });

  it("renders display block math with katex display mode", () => {
    const { container } = render(
      <MarkdownRenderer content={"$$\n\\int_0^\\infty e^{-x} \\, dx = 1\n$$"} />
    );
    const katexDisplay = container.querySelector(".katex-display");
    expect(katexDisplay).toBeInTheDocument();
  });
});
