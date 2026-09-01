import React, { createContext, useContext, useEffect, useState, useCallback } from "react";

export type Theme = "dark" | "light" | "system" | "high-contrast";
export type Density = "comfortable" | "cozy" | "compact";

interface ThemeContextType {
  theme: Theme;
  resolvedTheme: "dark" | "light" | "high-contrast";
  setTheme: (theme: Theme) => void;
  fontSize: number;
  setFontSize: (size: number) => void;
  density: Density;
  setDensity: (density: Density) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const getSystemTheme = (): "dark" | "light" => {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
};

const resolveTheme = (theme: Theme): "dark" | "light" | "high-contrast" => {
  if (theme === "high-contrast") return "high-contrast";
  if (theme === "system") return getSystemTheme();
  return theme;
};

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === "undefined") return "dark";
    return (localStorage.getItem("theme") as Theme) || "dark";
  });

  const [resolvedTheme, setResolvedTheme] = useState<"dark" | "light" | "high-contrast">(() => {
    if (typeof window === "undefined") return "dark";
    const stored = localStorage.getItem("theme") as Theme | null;
    return resolveTheme(stored || "dark");
  });

  const [fontSize, setFontSizeState] = useState<number>(() => {
    if (typeof window === "undefined") return 14;
    const saved = localStorage.getItem("font-size");
    return saved ? parseInt(saved, 10) : 14;
  });

  const [density, setDensityState] = useState<Density>(() => {
    if (typeof window === "undefined") return "comfortable";
    return (localStorage.getItem("ui-density") as Density) || "comfortable";
  });

  const applyTheme = useCallback(
    (newTheme: "dark" | "light" | "high-contrast", skipTransition = false) => {
      const root = window.document.documentElement;

      if (skipTransition) {
        root.classList.add("no-transition");
      }

      root.classList.remove("light", "dark", "high-contrast");
      root.classList.add(newTheme);
      root.style.colorScheme = newTheme === "high-contrast" ? "dark" : newTheme;
      root.setAttribute("data-theme", newTheme);

      if (skipTransition) {
        requestAnimationFrame(() => {
          root.classList.remove("no-transition");
        });
      }
    },
    [],
  );

  const setTheme = (newTheme: Theme) => {
    localStorage.setItem("theme", newTheme);
    setThemeState(newTheme);
    const resolved = resolveTheme(newTheme);
    setResolvedTheme(resolved);
    applyTheme(resolved);
  };

  const setFontSize = (size: number) => {
    localStorage.setItem("font-size", size.toString());
    setFontSizeState(size);
  };

  const setDensity = (newDensity: Density) => {
    localStorage.setItem("ui-density", newDensity);
    setDensityState(newDensity);
  };

  const toggleTheme = () => {
    const themes: Theme[] = ["dark", "light", "system", "high-contrast"];
    const currentIndex = themes.indexOf(theme);
    const nextIndex = (currentIndex + 1) % themes.length;
    setTheme(themes[nextIndex]);
  };

  // Sync density and font size to document element root
  useEffect(() => {
    const root = window.document.documentElement;

    // Sync font size
    root.style.fontSize = `${fontSize}px`;

    // Sync density
    root.classList.remove("density-comfortable", "density-cozy", "density-compact");
    root.classList.add(`density-${density}`);
  }, [fontSize, density]);

  useEffect(() => {
    const resolved = resolveTheme(theme);
    setResolvedTheme(resolved);
    applyTheme(resolved, true);

    if (theme === "system") {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      const listener = () => {
        const newResolved = getSystemTheme();
        setResolvedTheme(newResolved);
        applyTheme(newResolved);
      };
      mediaQuery.addEventListener("change", listener);
      return () => mediaQuery.removeEventListener("change", mediaQuery ? listener : () => {});
    }
    return undefined;
  }, [theme, applyTheme]);

  return (
    <ThemeContext.Provider
      value={{
        theme,
        resolvedTheme,
        setTheme,
        fontSize,
        setFontSize,
        density,
        setDensity,
        toggleTheme,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
};
