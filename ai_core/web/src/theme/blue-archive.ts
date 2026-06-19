import type { GlobalThemeOverrides } from 'naive-ui'

export const blueArchiveTheme: GlobalThemeOverrides = {
  common: {
    primaryColor: '#4C8FEC',
    primaryColorHover: '#6BA3F0',
    primaryColorPressed: '#2B6BC7',
    primaryColorSuppl: '#4C8FEC',
    borderRadius: '8px',
    borderRadiusSmall: '6px',
    fontFamily: '"Inter", "Noto Sans SC", system-ui, -apple-system, sans-serif',
  },
  Button: {
    borderRadiusMedium: '8px',
    borderRadiusSmall: '6px',
  },
  Card: {
    borderRadius: '12px',
  },
  DataTable: {
    borderRadius: '8px',
  },
  Input: {
    borderRadius: '8px',
  },
  Tag: {
    borderRadius: '6px',
  },
  Menu: {
    borderRadius: '8px',
  },
}
