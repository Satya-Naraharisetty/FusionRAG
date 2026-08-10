import React from "react";

/**
 * Decorative blinking cursor shown while tokens stream in.
 * The live text itself is announced via the parent list's aria-live region,
 * so the cursor is hidden from assistive tech.
 */
export const StreamingCursor: React.FC = () => {
  return <span className="streaming-cursor" aria-hidden="true" />;
};

export default StreamingCursor;
