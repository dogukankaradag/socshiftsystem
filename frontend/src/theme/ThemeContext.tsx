import { createContext, ReactNode, useContext, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';

type ThemeCtx = {
  theme: Theme;
  toggle: () => void;
  setTheme: (t: Theme) => void;
};

const Ctx = createContext<ThemeCtx | null>(null);

const STORAGE_KEY = 'vds.theme';

function readInitial(): Theme {
  if (typeof window === 'undefined') return 'light';
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    /* localStorage erişilemez (private mode vb.) — fallback'a geç */
  }
  // Sistem tercihini fallback olarak kullan
  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }
  return 'light';
}

function applyHtmlClass(theme: Theme) {
  const root = document.documentElement;
  if (theme === 'dark') root.classList.add('dark');
  else root.classList.remove('dark');
  // <meta name="color-scheme"> mobil tarayıcı UI'ını da ayarlar
  root.style.colorScheme = theme;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => readInitial());

  useEffect(() => {
    applyHtmlClass(theme);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* sessizce yut */
    }
  }, [theme]);

  // Sistem teması değişirse ve kullanıcı manuel seçim yapmadıysa takip et
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      try {
        // Kullanıcı kendi tercihini kaydettiyse sisteme uyma
        if (window.localStorage.getItem(STORAGE_KEY)) return;
      } catch {
        /* fall through */
      }
      setThemeState(e.matches ? 'dark' : 'light');
    };
    mq.addEventListener?.('change', handler);
    return () => mq.removeEventListener?.('change', handler);
  }, []);

  const value: ThemeCtx = {
    theme,
    toggle: () => setThemeState((t) => (t === 'dark' ? 'light' : 'dark')),
    setTheme: setThemeState,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
