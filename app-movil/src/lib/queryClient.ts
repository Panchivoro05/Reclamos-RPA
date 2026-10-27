import { QueryClient } from '@tanstack/react-query';

import { ApiError } from '@/api/cliente';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Reintenta solo fallos de red o del servidor; un 404 o 422 no mejora reintentando.
      retry: (intentos, error) =>
        intentos < 2 && (!(error instanceof ApiError) || error.status === 0 || error.status >= 500),
    },
  },
});
