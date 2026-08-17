import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'node_modules', 'backend']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // El patrón "derivar estado en useEffect" (sesión desde localStorage, fetching
      // inicial, cálculo de discrepancias) es intencional en este proyecto; la regla
      // nueva de react-hooks v7 lo marca como error sin ser un bug real.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
])
