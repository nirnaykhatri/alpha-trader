/**
 * Protected Route Wrapper Component
 * 
 * Ensures that only authenticated users can access protected content.
 * Shows appropriate loading and login states.
 * 
 * @module components/auth/protected-route
 */

'use client'

import React, { ReactNode } from 'react'
import { useAuth } from './auth-provider'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

interface ProtectedRouteProps {
  /** Content to render when authenticated */
  children: ReactNode
  /** Custom fallback component during loading */
  loadingFallback?: ReactNode
  /** Custom fallback component when not authenticated */
  unauthenticatedFallback?: ReactNode
  /** Bypass authentication in development mode */
  devBypass?: boolean
}

/**
 * Loading Skeleton Component
 * 
 * Shows a loading skeleton while authentication state is being determined.
 */
function LoadingSkeleton(): JSX.Element {
  return (
    <div className="h-screen w-full flex items-center justify-center bg-background">
      <div className="w-full max-w-md space-y-6 p-8">
        <div className="text-center space-y-2">
          <Skeleton className="h-8 w-48 mx-auto" />
          <Skeleton className="h-4 w-64 mx-auto" />
        </div>
        <Skeleton className="h-12 w-full" />
        <div className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      </div>
    </div>
  )
}

/**
 * Login Prompt Component
 * 
 * Shows a professional login interface when user is not authenticated.
 */
function LoginPrompt({ onLogin }: { onLogin: () => void }): JSX.Element {
  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-background via-background to-muted/20 p-4">
      <Card className="w-full max-w-md border-border/50 shadow-2xl">
        <CardHeader className="text-center space-y-4 pb-6">
          <div className="mx-auto w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center">
            <svg
              className="w-8 h-8 text-primary"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
          </div>
          <div>
            <CardTitle className="text-2xl font-bold">Alpha Trader Terminal</CardTitle>
            <CardDescription className="mt-2">
              Professional trading dashboard with real-time monitoring and controls
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-3 text-sm text-muted-foreground">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-profit/10 flex items-center justify-center">
                <svg className="w-4 h-4 text-profit" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
              <span>Real-time position monitoring</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-profit/10 flex items-center justify-center">
                <svg className="w-4 h-4 text-profit" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
              <span>Advanced DCA strategy controls</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-profit/10 flex items-center justify-center">
                <svg className="w-4 h-4 text-profit" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
              <span>Performance analytics & charts</span>
            </div>
          </div>

          <Button onClick={onLogin} className="w-full h-12 text-base font-medium" size="lg">
            <svg className="w-5 h-5 mr-2" viewBox="0 0 21 21" xmlns="http://www.w3.org/2000/svg">
              <rect x="1" y="1" width="9" height="9" fill="#f25022" />
              <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
              <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
              <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
            </svg>
            Sign in with Microsoft
          </Button>

          <p className="text-xs text-center text-muted-foreground">
            Protected by Azure Active Directory. Only authorized users can access this terminal.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Protected Route Component
 * 
 * Wraps content that requires authentication.
 * Handles loading states and shows appropriate UI based on auth status.
 * 
 * @param {ProtectedRouteProps} props - Component props
 * @returns {JSX.Element} Protected content or auth UI
 */
export function ProtectedRoute({
  children,
  loadingFallback,
  unauthenticatedFallback,
  devBypass = true,
}: ProtectedRouteProps): JSX.Element {
  const { isAuthenticated, isLoading, isConfigured, login } = useAuth()

  // Show loading state
  if (isLoading) {
    return loadingFallback ? <>{loadingFallback}</> : <LoadingSkeleton />
  }

  // Allow bypass in development if not configured
  if (!isConfigured && process.env.NODE_ENV === 'development' && devBypass) {
    return <>{children}</>
  }

  // Show login prompt if not authenticated
  if (!isAuthenticated) {
    return unauthenticatedFallback ? (
      <>{unauthenticatedFallback}</>
    ) : (
      <LoginPrompt onLogin={login} />
    )
  }

  // Render protected content
  return <>{children}</>
}

export default ProtectedRoute
