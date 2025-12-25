/**
 * Global Providers Component
 * 
 * Wraps the application with all necessary context providers
 * including authentication, theme, settings, and data fetching.
 * 
 * Provider Order (innermost to outermost access):
 * 1. AuthProvider - Authentication context
 * 2. AppSettingsProvider - Demo/Live mode and settings persistence
 * 3. ThemeProvider - Light/Dark/System theme management
 * 4. AdminApiProvider - Wires auth tokens and settings to API client
 * 5. ToastProvider - Toast notifications
 * 
 * @module app/providers
 */

'use client'

import React, { ReactNode, useEffect } from 'react'
import { AuthProvider, useAuth } from '@/components/auth'
import { ToastProvider, ToastViewport } from '@/components/ui/toast'
import { AppSettingsProvider, ThemeProvider } from '@/lib/contexts'
import { setTokenProvider, getAuthHeaders } from '@/lib/admin-api'
import { API_URL } from '@/lib/api'
import { updateAssetMetadataCache } from '@/lib/types/asset'

interface ProvidersProps {
  children: ReactNode
}

/**
 * Admin API Provider Component
 * 
 * Wires the authentication token provider to the admin API client.
 * Also loads centralized asset metadata from the backend.
 * Must be rendered inside AuthProvider to access getAccessToken.
 */
function AdminApiProvider({ children }: { children: ReactNode }): JSX.Element {
  const { getAccessToken, isAuthenticated } = useAuth()

  useEffect(() => {
    // Wire the token provider when auth is available
    if (isAuthenticated) {
      setTokenProvider(async () => {
        const token = await getAccessToken()
        return token || ''
      })
      
      // Load centralized asset metadata from backend
      loadAssetMetadata()
    }
  }, [getAccessToken, isAuthenticated])

  return <>{children}</>
}

/**
 * Load asset metadata from the backend API.
 * This populates the asset classification cache with the canonical
 * source of truth for symbol classification.
 */
async function loadAssetMetadata(): Promise<void> {
  try {
    const headers = await getAuthHeaders()
    const response = await fetch(`${API_URL}/admin/asset-metadata`, {
      headers,
    })
    
    if (response.ok) {
      const data = await response.json()
      updateAssetMetadataCache({
        knownSymbols: data.knownSymbols,
      })
      console.log('[AssetMetadata] Loaded centralized asset metadata from API')
    } else {
      console.warn('[AssetMetadata] Failed to load from API, using local fallback')
    }
  } catch (error) {
    // Silent fail - local heuristics will be used as fallback
    console.warn('[AssetMetadata] API unavailable, using local fallback')
  }
}

/**
 * Global Providers Component
 * 
 * Combines all app-level providers into a single wrapper.
 * Order matters - providers lower in the tree can access providers above them.
 * 
 * Provider Order:
 * 1. AuthProvider - Provides authentication context
 * 2. AppSettingsProvider - Demo/Live mode and settings
 * 3. ThemeProvider - Theme management (depends on AppSettings)
 * 4. AdminApiProvider - Wires auth tokens to API client
 * 5. ToastProvider - Provides toast notifications
 * 
 * @param {ProvidersProps} props - Component props
 * @returns {JSX.Element} Provider-wrapped children
 */
export function Providers({ children }: ProvidersProps): JSX.Element {
  return (
    <AuthProvider>
      <AppSettingsProvider>
        <ThemeProvider attribute="class" defaultTheme="dark" enableTransitions>
          <AdminApiProvider>
            <ToastProvider>
              {children}
              <ToastViewport />
            </ToastProvider>
          </AdminApiProvider>
        </ThemeProvider>
      </AppSettingsProvider>
    </AuthProvider>
  )
}
