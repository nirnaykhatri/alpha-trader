/**
 * Authentication Provider Component
 * 
 * Wraps the application with MSAL authentication context and provides
 * authentication state to all child components.
 * 
 * @module components/auth/auth-provider
 */

'use client'

import React, { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'
import {
  PublicClientApplication,
  AccountInfo,
  InteractionStatus,
  EventType,
  AuthenticationResult,
  InteractionRequiredAuthError,
} from '@azure/msal-browser'
import { msalConfig, loginRequest, isMsalConfigured, getMsalConfigStatus } from '@/lib/auth/msal-config'

/**
 * Authentication Context Interface
 * 
 * Defines the shape of the authentication context available throughout the app.
 */
interface AuthContextType {
  /** Whether user is currently authenticated */
  isAuthenticated: boolean
  /** Whether authentication is in progress */
  isLoading: boolean
  /** Current user account information */
  account: AccountInfo | null
  /** Error message if authentication failed */
  error: string | null
  /** Whether MSAL is properly configured */
  isConfigured: boolean
  /** Initiates login flow */
  login: () => Promise<void>
  /** Initiates logout flow */
  logout: () => Promise<void>
  /** Gets access token for API calls */
  getAccessToken: () => Promise<string | null>
  /** User's display name */
  userName: string
  /** User's email address */
  userEmail: string
  /** User's profile picture URL (if available) */
  userPhoto: string | null
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

let msalInstance: PublicClientApplication | null = null

/**
 * Gets or creates the MSAL instance (singleton pattern)
 */
const getMsalInstance = (): PublicClientApplication | null => {
  if (typeof window === 'undefined') return null
  
  if (!isMsalConfigured()) {
    console.warn('MSAL not configured:', getMsalConfigStatus())
    return null
  }
  
  if (!msalInstance) {
    msalInstance = new PublicClientApplication(msalConfig)
  }
  return msalInstance
}

interface AuthProviderProps {
  children: ReactNode
}

/**
 * Authentication Provider Component
 * 
 * Provides authentication context to the entire application.
 * Handles MSAL initialization, login, logout, and token acquisition.
 * 
 * @param {AuthProviderProps} props - Component props
 * @returns {JSX.Element} Provider component wrapping children
 */
export function AuthProvider({ children }: AuthProviderProps): JSX.Element {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [account, setAccount] = useState<AccountInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [initialized, setInitialized] = useState(false)

  const isConfigured = isMsalConfigured()

  /**
   * Initialize MSAL and check for existing sessions
   */
  useEffect(() => {
    const initialize = async () => {
      const instance = getMsalInstance()
      
      if (!instance) {
        setIsLoading(false)
        return
      }

      try {
        // Handle redirect promise (for redirect-based auth)
        await instance.initialize()
        const response = await instance.handleRedirectPromise()
        
        if (response) {
          setAccount(response.account)
          setIsAuthenticated(true)
        } else {
          // Check for existing accounts
          const accounts = instance.getAllAccounts()
          if (accounts.length > 0) {
            setAccount(accounts[0])
            setIsAuthenticated(true)
          }
        }

        // Set up event callbacks
        instance.addEventCallback((event) => {
          if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
            const payload = event.payload as AuthenticationResult
            setAccount(payload.account)
            setIsAuthenticated(true)
          }
          if (event.eventType === EventType.LOGOUT_SUCCESS) {
            setAccount(null)
            setIsAuthenticated(false)
          }
        })

        setInitialized(true)
      } catch (err) {
        console.error('MSAL initialization error:', err)
        setError(err instanceof Error ? err.message : 'Authentication initialization failed')
      } finally {
        setIsLoading(false)
      }
    }

    initialize()
  }, [])

  /**
   * Login handler - initiates popup-based login flow
   */
  const login = useCallback(async () => {
    const instance = getMsalInstance()
    if (!instance) {
      setError('Authentication not configured')
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      const response = await instance.loginPopup(loginRequest)
      setAccount(response.account)
      setIsAuthenticated(true)
    } catch (err) {
      console.error('Login error:', err)
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setIsLoading(false)
    }
  }, [])

  /**
   * Logout handler - clears session and redirects
   */
  const logout = useCallback(async () => {
    const instance = getMsalInstance()
    if (!instance || !account) return

    setIsLoading(true)

    try {
      await instance.logoutPopup({
        account: account,
        postLogoutRedirectUri: window.location.origin,
      })
      setAccount(null)
      setIsAuthenticated(false)
    } catch (err) {
      console.error('Logout error:', err)
      setError(err instanceof Error ? err.message : 'Logout failed')
    } finally {
      setIsLoading(false)
    }
  }, [account])

  /**
   * Gets an access token for API calls
   * 
   * Attempts silent token acquisition first, falls back to interactive.
   * 
   * @returns {Promise<string | null>} Access token or null if failed
   */
  const getAccessToken = useCallback(async (): Promise<string | null> => {
    const instance = getMsalInstance()
    if (!instance || !account) return null

    try {
      const response = await instance.acquireTokenSilent({
        ...loginRequest,
        account: account,
      })
      return response.accessToken
    } catch (err) {
      if (err instanceof InteractionRequiredAuthError) {
        try {
          const response = await instance.acquireTokenPopup(loginRequest)
          return response.accessToken
        } catch (popupErr) {
          console.error('Token acquisition failed:', popupErr)
          return null
        }
      }
      console.error('Silent token acquisition failed:', err)
      return null
    }
  }, [account])

  const userName = account?.name || 'User'
  const userEmail = account?.username || ''
  const userPhoto = null // Would require Graph API call for actual photo

  const contextValue: AuthContextType = {
    isAuthenticated,
    isLoading,
    account,
    error,
    isConfigured,
    login,
    logout,
    getAccessToken,
    userName,
    userEmail,
    userPhoto,
  }

  return <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>
}

/**
 * Authentication Hook
 * 
 * Provides access to authentication context from any component.
 * Must be used within an AuthProvider.
 * 
 * @returns {AuthContextType} Authentication context
 * @throws {Error} If used outside of AuthProvider
 */
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

/**
 * Higher-Order Component for Protected Routes
 * 
 * Wraps a component to ensure user is authenticated before rendering.
 * Shows loading state while checking authentication.
 * Redirects to login if not authenticated.
 * 
 * @param {React.ComponentType<P>} WrappedComponent - Component to protect
 * @returns {React.FC<P>} Protected component
 */
export function withAuth<P extends object>(
  WrappedComponent: React.ComponentType<P>
): React.FC<P> {
  return function ProtectedComponent(props: P) {
    const { isAuthenticated, isLoading, login, isConfigured } = useAuth()

    if (isLoading) {
      return (
        <div className="flex h-screen items-center justify-center">
          <div className="text-center">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto mb-4" />
            <p className="text-muted-foreground">Loading authentication...</p>
          </div>
        </div>
      )
    }

    // In development, allow bypass if not configured
    if (!isConfigured && process.env.NODE_ENV === 'development') {
      return <WrappedComponent {...props} />
    }

    if (!isAuthenticated) {
      return (
        <div className="flex h-screen items-center justify-center bg-background">
          <div className="text-center space-y-6 p-8 rounded-xl border bg-card max-w-md">
            <div className="space-y-2">
              <h1 className="text-2xl font-bold">Trading Terminal</h1>
              <p className="text-muted-foreground">
                Sign in with your Microsoft account to access the trading dashboard.
              </p>
            </div>
            <button
              onClick={login}
              className="w-full px-6 py-3 bg-primary text-primary-foreground rounded-md font-medium hover:bg-primary/90 transition-colors flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5" viewBox="0 0 21 21" xmlns="http://www.w3.org/2000/svg">
                <rect x="1" y="1" width="9" height="9" fill="#f25022" />
                <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
                <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
                <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
              </svg>
              Sign in with Microsoft
            </button>
          </div>
        </div>
      )
    }

    return <WrappedComponent {...props} />
  }
}
