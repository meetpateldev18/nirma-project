/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Institutional University Brand & Accent
        primary: {
          DEFAULT: '#E06D3B',
          hover: '#F08252',
          deep: '#993416',
          foreground: '#FFFFFF',
        },
        nirma: {
          navy: '#16254D',
          'navy-soft': '#47547A',
          terracotta: '#E06D3B',
        },
        // Telemetry & Real-Time Voice Stream Accents — deepened from their original
        // dark-canvas values so each still clears WCAG AA as text on a light surface.
        'live-pulse': {
          DEFAULT: '#047857',
          soft: '#059669',
        },
        telemetry: {
          cyan: '#0E7490',
          'cyan-soft': '#0891B2',
          amber: '#B45309',
          violet: '#7C3AED',
          emerald: '#047857',
          rose: '#DC2626',
        },
        // Canvas & Surface System — light "paper" hierarchy: a soft page ground, white
        // cards/bars raised off it, and a faint recessed tone for nested controls.
        canvas: {
          DEFAULT: '#EEF1F6',
          subtle: '#FFFFFF',
          soft: '#FFFFFF',
          elevated: '#F1F3F8',
          overlay: 'rgba(22, 37, 77, 0.45)',
        },
        // Hairline Borders & Dividers
        hairline: {
          DEFAULT: 'rgba(15, 23, 42, 0.10)',
          subtle: 'rgba(15, 23, 42, 0.06)',
          strong: 'rgba(15, 23, 42, 0.16)',
          terracotta: 'rgba(224, 109, 59, 0.35)',
        },
        // Text & Content Scale
        ink: {
          DEFAULT: '#16254D',
          strong: '#0B1530',
        },
        body: '#47547A',
        mute: '#8891A6',
        disabled: '#B7BECC',
        // Telecom Call State Semantic Tokens
        state: {
          queued: '#2563EB',
          ringing: '#B45309',
          'in-progress': '#047857',
          completed: '#15803D',
          failed: '#DC2626',
          busy: '#7C3AED',
          dnd: '#475569',
        },
        border: 'rgba(15, 23, 42, 0.10)',
        input: 'rgba(15, 23, 42, 0.10)',
        ring: '#E06D3B',
        background: '#EEF1F6',
        foreground: '#16254D',
        // Aliases kept for the "New Call" flow's editorial styling (serif headlines,
        // warm opening-line callout) — same values as the scale above.
        paper: {
          DEFAULT: '#EEF1F6',
          raised: '#FFFFFF',
          soft: '#F1F3F8',
        },
        navy: {
          DEFAULT: '#16254D',
          soft: '#47547A',
          mute: '#8891A6',
        },
        paperline: {
          DEFAULT: 'rgba(15, 23, 42, 0.10)',
          strong: 'rgba(15, 23, 42, 0.16)',
        },
        gold: {
          DEFAULT: '#C9992D',
          soft: '#F4E7C9',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Noto Sans Gujarati', 'Noto Sans Devanagari', 'sans-serif'],
        mono: ['"SFMono-Regular"', 'Menlo', 'Monaco', 'Consolas', '"JetBrains Mono"', 'monospace'],
        serif: ['"Source Serif 4"', 'ui-serif', 'Georgia', 'serif'],
      },
      borderRadius: {
        xs: '2px',
        sm: '4px',
        DEFAULT: '6px',
        md: '8px',
        lg: '12px',
        xl: '16px',
        pill: '9999px',
      },
      height: {
        control: '32px',
        'control-lg': '40px',
      },
      animation: {
        'pulse-subtle': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        soundwave: 'soundwave 1.2s ease-in-out infinite alternate',
      },
      keyframes: {
        soundwave: {
          '0%': { height: '4px' },
          '100%': { height: '24px' },
        },
      },
    },
  },
  plugins: [],
};
