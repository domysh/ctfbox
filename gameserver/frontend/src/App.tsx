import '@mantine/core/styles.css';
import '@mantine/charts/styles.css';

import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import {
  QueryClient,
  QueryClientProvider
} from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import './styles/main.css';
import { MainLayout } from './components/MainLayout';

const queryClient = new QueryClient()

// Helper text goes under the field instead of over it: read down a column of
// inputs, a field that has a description (or whose text wraps) would otherwise
// push its input out of line with its neighbours in the same grid row.
const theme = {
  components: {
    InputWrapper: {
      defaultProps: {
        inputWrapperOrder: ['label', 'input', 'description', 'error'],
      },
    },
  },
}

export default function App() {
  return <MantineProvider defaultColorScheme='dark' theme={theme}>
    <ModalsProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<MainLayout page='rules' />} />
            <Route path="/rules" element={<MainLayout page='rules' />} />
            <Route path="/scoreboard" element={<MainLayout page='scoreboard' />} />
            <Route path="/scoreboard/team/:teamId" element={<MainLayout page='scoreboard-team' />} />
            <Route path="/admin" element={<MainLayout page='admin' />} />
            <Route path="*" element={<MainLayout page='not-found' />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ModalsProvider>
  </MantineProvider> 
}

