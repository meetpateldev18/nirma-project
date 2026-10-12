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
          DEFAULT: '#2F5BEA',
          hover: '#2449C8',
          deep: '#1B38A0',
          foreground: '#FFFFFF',
        },
        nirma: {
          navy: '#16254D',
          'navy-soft': '#47547A',
          terracotta: '#2F5BEA',
        },
        // Telemetry & Real-Time Voice Stream Accents — deepened from their original
        // dark-canvas values so each still clears WCAG AA as text on a light surface.
        'live-pulse': {
          DEFAULT: '#12A150',
          soft: '#16A765',
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
          DEFAULT: '#F4F4F5',
          subtle: '#FFFFFF',
          soft: '#FFFFFF',
          elevated: '#F3F4F6',
          overlay: 'rgba(22, 37, 77, 0.45)',
        },
        // Hairline Borders & Dividers
        hairline: {
          DEFAULT: 'rgba(15, 23, 42, 0.07)',
          subtle: 'rgba(15, 23, 42, 0.06)',
          strong: 'rgba(15, 23, 42, 0.16)',
          terracotta: 'rgba(47, 91, 234, 0.35)',
        },
        // Text & Content Scale
        ink: {
          DEFAULT: '#1F2430',
          strong: '#11141C',
        },
        body: '#5B6270',
        mute: '#9AA0AB',
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
        ring: '#2F5BEA',
        background: '#F4F4F5',
        foreground: '#1F2430',
        // Aliases kept for the "New Call" flow's editorial styling (serif headlines,
        // warm opening-line callout) — same values as the scale above.
        paper: {
          DEFAULT: '#F4F4F5',
          raised: '#FFFFFF',
          soft: '#F3F4F6',
        },
        navy: {
          DEFAULT: '#1F2430',
          soft: '#5B6270',
          mute: '#9AA0AB',
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
