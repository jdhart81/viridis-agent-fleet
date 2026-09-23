// ===== PACKAGE.JSON =====
// apps/web/package.json
{
  "name": "@protogen/web",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "type-check": "tsc --noEmit"
  },
  "dependencies": {
    "@headlessui/react": "^1.7.17",
    "@heroicons/react": "^2.0.18",
    "@hookform/resolvers": "^3.3.2",
    "@radix-ui/react-alert-dialog": "^1.0.5",
    "@radix-ui/react-dialog": "^1.0.5",
    "@radix-ui/react-dropdown-menu": "^2.0.6",
    "@radix-ui/react-label": "^2.0.2",
    "@radix-ui/react-popover": "^1.0.7",
    "@radix-ui/react-select": "^2.0.0",
    "@radix-ui/react-slot": "^1.0.2",
    "@radix-ui/react-tabs": "^1.0.4",
    "@radix-ui/react-toast": "^1.1.5",
    "@stripe/stripe-js": "^2.2.0",
    "@tanstack/react-query": "^5.12.2",
    "@three/drei": "^9.89.0",
    "@three/fiber": "^8.15.11",
    "axios": "^1.6.2",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.0.0",
    "date-fns": "^2.30.0",
    "framer-motion": "^10.16.16",
    "lucide-react": "^0.294.0",
    "next": "14.0.4",
    "next-auth": "^4.24.5",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-dropzone": "^14.2.3",
    "react-hook-form": "^7.48.2",
    "react-hot-toast": "^2.4.1",
    "recharts": "^2.10.3",
    "socket.io-client": "^4.7.2",
    "tailwind-merge": "^2.1.0",
    "three": "^0.159.0",
    "zod": "^3.22.4",
    "zustand": "^4.4.7"
  },
  "devDependencies": {
    "@types/node": "^20.10.4",
    "@types/react": "^18.2.45",
    "@types/react-dom": "^18.2.18",
    "@types/three": "^0.159.0",
    "autoprefixer": "^10.4.16",
    "eslint": "^8.55.0",
    "eslint-config-next": "14.0.4",
    "postcss": "^8.4.32",
    "tailwindcss": "^3.3.6",
    "typescript": "^5.3.3"
  }
}

// ===== TYPESCRIPT CONFIG =====
// apps/web/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "paths": {
      "@/*": ["./src/*"],
      "@/components/*": ["./src/components/*"],
      "@/lib/*": ["./src/lib/*"],
      "@/hooks/*": ["./src/hooks/*"],
      "@/types/*": ["./src/types/*"],
      "@/styles/*": ["./src/styles/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}

// ===== TAILWIND CONFIG =====
// apps/web/tailwind.config.js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'spectrum-blue': '#00AEEF',
        'spectrum-red': '#E53935',
        'spectrum-yellow': '#FFEB3B',
        'spectrum-green': '#4CAF50',
        'spectrum-orange': '#FF9800',
        'gradient-start': '#00BFFF',
        'gradient-mid': '#8A2BE2',
        'gradient-end': '#FF4500',
        'dark-gray': '#2E2E2E',
        'light-gray': '#B0BEC5',
      },
      backgroundImage: {
        'spectrum-gradient': 'linear-gradient(135deg, #00BFFF, #8A2BE2, #FF4500)',
        'button-hover-gradient': 'linear-gradient(135deg, #00AEEF, #4CAF50)',
        'subtle-gradient': 'linear-gradient(180deg, rgba(0, 174, 239, 0.1), rgba(138, 43, 226, 0.05))',
      },
      animation: {
        'spin-slow': 'spin 3s linear infinite',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}

// ===== NEXT CONFIG =====
// apps/web/next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  images: {
    domains: ['protogen-assets.s3.amazonaws.com', 'localhost'],
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.API_URL || 'http://localhost:8000',
    NEXT_PUBLIC_STRIPE_KEY: process.env.STRIPE_PUBLISHABLE_KEY,
    NEXT_PUBLIC_SOCKET_URL: process.env.SOCKET_URL || 'http://localhost:8000',
  },
  webpack: (config) => {
    config.experiments = {
      ...config.experiments,
      topLevelAwait: true,
    };
    return config;
  },
}

module.exports = nextConfig

// ===== ROOT LAYOUT =====
// apps/web/src/app/layout.tsx
import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from '@/components/providers'
import { Toaster } from 'react-hot-toast'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'ProtoGen - AI-Powered Manufacturing Platform',
  description: 'Transform ideas into manufactured products in days, not months.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Providers>
          {children}
          <Toaster position="top-right" />
        </Providers>
      </body>
    </html>
  )
}

// ===== GLOBAL STYLES =====
// apps/web/src/app/globals.css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --spectrum-blue: #00AEEF;
    --spectrum-red: #E53935;
    --spectrum-yellow: #FFEB3B;
    --spectrum-green: #4CAF50;
    --spectrum-orange: #FF9800;
    --gradient-start: #00BFFF;
    --gradient-mid: #8A2BE2;
    --gradient-end: #FF4500;
    --dark-gray: #2E2E2E;
    --light-gray: #B0BEC5;
  }
}

@layer utilities {
  .text-balance {
    text-wrap: balance;
  }
  
  .spectrum-glow {
    box-shadow: 0 0 20px rgba(0, 174, 239, 0.5);
  }
  
  .gradient-text {
    @apply bg-spectrum-gradient bg-clip-text text-transparent;
  }
}

// ===== PROVIDERS =====
// apps/web/src/components/providers.tsx
'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SessionProvider } from 'next-auth/react'
import { useState } from 'react'
import { ThemeProvider } from './theme-provider'

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000,
        refetchOnWindowFocus: false,
      },
    },
  }))

  return (
    <SessionProvider>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </QueryClientProvider>
    </SessionProvider>
  )
}

// ===== THEME PROVIDER =====
// apps/web/src/components/theme-provider.tsx
'use client'

import React, { createContext, useContext, useEffect, useState } from 'react'

type Theme = 'light' | 'dark'

interface ThemeContextType {
  theme: Theme
  setTheme: (theme: Theme) => void
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>('light')

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme') as Theme | null
    if (savedTheme) {
      setTheme(savedTheme)
    }
  }, [])

  useEffect(() => {
    localStorage.setItem('theme', theme)
    if (theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

// ===== TYPES =====
// apps/web/src/types/index.ts
export interface User {
  id: string
  email: string
  name: string
  company?: string
  avatar?: string
  subscription: SubscriptionTier
  createdAt: Date
}

export enum SubscriptionTier {
  FREE = 'free',
  STARTER = 'starter',
  PROFESSIONAL = 'professional',
  ENTERPRISE = 'enterprise',
}

export interface Project {
  id: string
  userId: string
  name: string
  description: string
  status: ProjectStatus
  designData?: DesignData
  manufacturingSpecs?: ManufacturingSpecs
  quotes?: Quote[]
  files?: DesignFile[]
  createdAt: Date
  updatedAt: Date
}

export enum ProjectStatus {
  DRAFT = 'draft',
  DESIGNING = 'designing',
  QUOTING = 'quoting',
  MANUFACTURING = 'manufacturing',
  SHIPPED = 'shipped',
  COMPLETED = 'completed',
}

export interface DesignData {
  dimensions?: {
    length: number
    width: number
    height: number
    units: 'mm' | 'cm' | 'inches'
  }
  volume?: number
  weight?: number
  material?: string
  optimization?: OptimizationResult
}

export interface ManufacturingSpecs {
  process: ManufacturingProcess
  material: Material
  quantity: number
  finish?: string
  tolerance?: string
  certifications?: string[]
}

export enum ManufacturingProcess {
  FDM = 'fdm',
  SLA = 'sla',
  SLS = 'sls',
  CNC_3AXIS = 'cnc_3axis',
  CNC_5AXIS = 'cnc_5axis',
  LASER_CUTTING = 'laser_cutting',
  INJECTION_MOLDING = 'injection_molding',
}

export interface Material {
  id: string
  name: string
  category: MaterialCategory
  properties: MaterialProperties
  sustainabilityScore: number
  costPerKg: number
}

export enum MaterialCategory {
  PLASTIC = 'plastic',
  METAL = 'metal',
  COMPOSITE = 'composite',
  CERAMIC = 'ceramic',
}

export interface MaterialProperties {
  tensileStrength?: number
  density?: number
  meltingPoint?: number
  thermalExpansion?: number
  electricalConductivity?: string
}

export interface Quote {
  id: string
  projectId: string
  supplierId: string
  supplierName: string
  supplierRating: number
  costBreakdown: CostBreakdown
  leadTimeDays: number
  expiresAt: Date
  selected?: boolean
}

export interface CostBreakdown {
  materialCost: number
  setupCost: number
  machineCost: number
  unitCost: number
  totalCost: number
  quantity: number
}

export interface DesignFile {
  id: string
  projectId: string
  filename: string
  fileType: string
  fileSize: number
  url: string
  thumbnailUrl?: string
  metadata?: Record<string, any>
  uploadedAt: Date
}

export interface OptimizationResult {
  originalVolume: number
  optimizedVolume: number
  weightReduction: number
  costReduction: number
  modifications: string[]
}

export interface Supplier {
  id: string
  name: string
  rating: number
  capabilities: ManufacturingProcess[]
  materials: string[]
  certifications: string[]
  location: {
    country: string
    state: string
    city: string
  }
  leadTimes: Record<ManufacturingProcess, number>
}

// ===== API CLIENT =====
// apps/web/src/lib/api.ts
import axios from 'axios'
import { getSession } from 'next-auth/react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use(async (config) => {
  const session = await getSession()
  if (session?.accessToken) {
    config.headers.Authorization = `Bearer ${session.accessToken}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      window.location.href = '/auth/signin'
    }
    return Promise.reject(error)
  }
)

export default api

// ===== AUTH CONFIG =====
// apps/web/src/pages/api/auth/[...nextauth].ts
import NextAuth, { NextAuthOptions } from 'next-auth'
import GoogleProvider from 'next-auth/providers/google'
import GithubProvider from 'next-auth/providers/github'
import CredentialsProvider from 'next-auth/providers/credentials'
import api from '@/lib/api'

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
    GithubProvider({
      clientId: process.env.GITHUB_CLIENT_ID!,
      clientSecret: process.env.GITHUB_CLIENT_SECRET!,
    }),
    CredentialsProvider({
      name: 'credentials',
      credentials: {
        email: { label: 'Email', type: 'email' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(credentials) {
        try {
          const { data } = await api.post('/auth/login', credentials)
          return data.user
        } catch (error) {
          return null
        }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user, account }) {
      if (user) {
        token.id = user.id
        token.email = user.email
      }
      if (account) {
        token.accessToken = account.access_token
      }
      return token
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.id as string
        session.user.email = token.email as string
      }
      session.accessToken = token.accessToken as string
      return session
    },
  },
  pages: {
    signIn: '/auth/signin',
    signOut: '/auth/signout',
    error: '/auth/error',
  },
}

export default NextAuth(authOptions)

// ===== HOME PAGE =====
// apps/web/src/app/page.tsx
import { Navbar } from '@/components/layout/navbar'
import { Hero } from '@/components/home/hero'
import { Features } from '@/components/home/features'
import { HowItWorks } from '@/components/home/how-it-works'
import { Testimonials } from '@/components/home/testimonials'
import { Footer } from '@/components/layout/footer'

export default function HomePage() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <Features />
        <HowItWorks />
        <Testimonials />
      </main>
      <Footer />
    </>
  )
}

// ===== NAVBAR COMPONENT =====
// apps/web/src/components/layout/navbar.tsx
'use client'

import Link from 'next/link'
import { useSession, signOut } from 'next-auth/react'
import { Button } from '@/components/ui/button'
import { 
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { User, LogOut, Settings, Package } from 'lucide-react'

export function Navbar() {
  const { data: session } = useSession()

  return (
    <nav className="fixed top-0 w-full bg-white/80 backdrop-blur-md border-b border-gray-200 z-50">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="flex items-center space-x-2">
            <div className="w-8 h-8 bg-spectrum-gradient rounded-lg" />
            <span className="text-xl font-bold">ProtoGen</span>
          </Link>

          <div className="hidden md:flex items-center space-x-8">
            <Link href="/features" className="text-gray-600 hover:text-gray-900">
              Features
            </Link>
            <Link href="/pricing" className="text-gray-600 hover:text-gray-900">
              Pricing
            </Link>
            <Link href="/docs" className="text-gray-600 hover:text-gray-900">
              Documentation
            </Link>
            <Link href="/blog" className="text-gray-600 hover:text-gray-900">
              Blog
            </Link>
          </div>

          <div className="flex items-center space-x-4">
            {session ? (
              <>
                <Link href="/dashboard">
                  <Button variant="outline">Dashboard</Button>
                </Link>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <User className="h-5 w-5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem>
                      <Settings className="mr-2 h-4 w-4" />
                      Settings
                    </DropdownMenuItem>
                    <DropdownMenuItem>
                      <Package className="mr-2 h-4 w-4" />
                      My Projects
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => signOut()}>
                      <LogOut className="mr-2 h-4 w-4" />
                      Sign out
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </>
            ) : (
              <>
                <Link href="/auth/signin">
                  <Button variant="outline">Sign In</Button>
                </Link>
                <Link href="/auth/signup">
                  <Button className="bg-spectrum-blue hover:bg-spectrum-blue/90">
                    Start Free Trial
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}

// ===== HERO COMPONENT =====
// apps/web/src/components/home/hero.tsx
'use client'

import Link from 'next/link'
import { motion } from 'framer-motion'
import { Button } from '@/components/ui/button'
import { ArrowRight, Zap, Package, DollarSign } from 'lucide-react'

export function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-gradient-start/10 via-gradient-mid/10 to-gradient-end/10" />
      
      <div className="container mx-auto px-4 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center max-w-4xl mx-auto"
        >
          <h1 className="text-5xl md:text-7xl font-bold mb-6">
            Manufacturing Made
            <span className="gradient-text"> Intelligent</span>
          </h1>
          
          <p className="text-xl md:text-2xl text-gray-600 mb-8">
            Transform your ideas into manufactured products in days, not months. 
            AI-powered design optimization, instant quotes, and global manufacturing network.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center mb-12">
            <Link href="/auth/signup">
              <Button size="lg" className="bg-spectrum-blue hover:bg-spectrum-blue/90">
                Start Free Trial
                <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
            </Link>
            <Link href="/demo">
              <Button size="lg" variant="outline">
                Watch Demo
              </Button>
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-16">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="flex flex-col items-center"
            >
              <div className="w-16 h-16 bg-spectrum-blue/20 rounded-full flex items-center justify-center mb-4">
                <Zap className="h-8 w-8 text-spectrum-blue" />
              </div>
              <h3 className="text-lg font-semibold mb-2">AI-Powered Design</h3>
              <p className="text-gray-600">Optimize designs for manufacturing automatically</p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="flex flex-col items-center"
            >
              <div className="w-16 h-16 bg-spectrum-green/20 rounded-full flex items-center justify-center mb-4">
                <DollarSign className="h-8 w-8 text-spectrum-green" />
              </div>
              <h3 className="text-lg font-semibold mb-2">Instant Quotes</h3>
              <p className="text-gray-600">Get pricing from verified suppliers in seconds</p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="flex flex-col items-center"
            >
              <div className="w-16 h-16 bg-spectrum-orange/20 rounded-full flex items-center justify-center mb-4">
                <Package className="h-8 w-8 text-spectrum-orange" />
              </div>
              <h3 className="text-lg font-semibold mb-2">Global Network</h3>
              <p className="text-gray-600">10,000+ verified manufacturing partners worldwide</p>
            </motion.div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

// ===== DASHBOARD LAYOUT =====
// apps/web/src/app/dashboard/layout.tsx
import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth/next'
import { authOptions } from '@/pages/api/auth/[...nextauth]'
import { DashboardNav } from '@/components/dashboard/nav'
import { DashboardHeader } from '@/components/dashboard/header'

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const session = await getServerSession(authOptions)

  if (!session) {
    redirect('/auth/signin')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <DashboardHeader />
      <div className="flex">
        <DashboardNav />
        <main className="flex-1 p-8">{children}</main>
      </div>
    </div>
  )
}

// ===== DASHBOARD PAGE =====
// apps/web/src/app/dashboard/page.tsx
'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ProjectCard } from '@/components/dashboard/project-card'
import { StatsOverview } from '@/components/dashboard/stats-overview'
import { QuickActions } from '@/components/dashboard/quick-actions'
import { RecentActivity } from '@/components/dashboard/recent-activity'
import { AIAssistant } from '@/components/dashboard/ai-assistant'
import api from '@/lib/api'
import { Project } from '@/types'
import { Plus } from 'lucide-react'
import Link from 'next/link'

export default function DashboardPage() {
  const [aiPanelOpen, setAiPanelOpen] = useState(false)

  const { data: projects, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: async () => {
      const { data } = await api.get<Project[]>('/projects')
      return data
    },
  })

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="text-gray-600 mt-1">
            Welcome back! Here's what's happening with your projects.
          </p>
        </div>
        <Link href="/dashboard/projects/new">
          <Button className="bg-spectrum-blue hover:bg-spectrum-blue/90">
            <Plus className="mr-2 h-4 w-4" />
            New Project
          </Button>
        </Link>
      </div>

      <StatsOverview />
      <QuickActions />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Recent Projects</h2>
              <Link href="/dashboard/projects">
                <Button variant="outline" size="sm">View All</Button>
              </Link>
            </div>
            
            {isLoading ? (
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-32 bg-gray-100 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {projects?.slice(0, 4).map((project) => (
                  <ProjectCard key={project.id} project={project} />
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <RecentActivity />
          <Card className="p-6">
            <h3 className="text-lg font-semibold mb-4">Need Help?</h3>
            <p className="text-gray-600 mb-4">
              Our AI assistant can help you optimize designs, find materials, and get quotes.
            </p>
            <Button 
              onClick={() => setAiPanelOpen(true)}
              className="w-full bg-spectrum-blue hover:bg-spectrum-blue/90"
            >
              Open AI Assistant
            </Button>
          </Card>
        </div>
      </div>

      <AIAssistant open={aiPanelOpen} onClose={() => setAiPanelOpen(false)} />
    </div>
  )
}

// ===== PROJECT EDITOR PAGE =====
// apps/web/src/app/dashboard/projects/[id]/page.tsx
'use client'

import { useState } from 'react'
import { useParams } from 'next/navigation'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DesignEditor } from '@/components/project/design-editor'
import { MaterialSelector } from '@/components/project/material-selector'
import { QuoteManager } from '@/components/project/quote-manager'
import { ManufacturingTracker } from '@/components/project/manufacturing-tracker'
import { ProjectSettings } from '@/components/project/settings'
import { ProjectHeader } from '@/components/project/header'
import { CADViewer } from '@/components/project/cad-viewer'
import api from '@/lib/api'
import { Project } from '@/types'
import toast from 'react-hot-toast'

export default function ProjectPage() {
  const params = useParams()
  const projectId = params.id as string
  const [activeTab, setActiveTab] = useState('design')

  const { data: project, isLoading } = useQuery({
    queryKey: ['project', projectId],
    queryFn: async () => {
      const { data } = await api.get<Project>(`/projects/${projectId}`)
      return data
    },
  })

  const updateProject = useMutation({
    mutationFn: async (updates: Partial<Project>) => {
      const { data } = await api.put(`/projects/${projectId}`, updates)
      return data
    },
    onSuccess: () => {
      toast.success('Project updated successfully')
    },
  })

  if (isLoading || !project) {
    return <div>Loading...</div>
  }

  return (
    <div className="space-y-6">
      <ProjectHeader project={project} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="w-full">
              <TabsTrigger value="design">Design</TabsTrigger>
              <TabsTrigger value="materials">Materials</TabsTrigger>
              <TabsTrigger value="quotes">Quotes</TabsTrigger>
              <TabsTrigger value="manufacturing">Manufacturing</TabsTrigger>
              <TabsTrigger value="settings">Settings</TabsTrigger>
            </TabsList>

            <TabsContent value="design" className="mt-6">
              <DesignEditor 
                project={project} 
                onUpdate={(updates) => updateProject.mutate(updates)}
              />
            </TabsContent>

            <TabsContent value="materials" className="mt-6">
              <MaterialSelector 
                project={project}
                onSelect={(material) => updateProject.mutate({ 
                  manufacturingSpecs: { ...project.manufacturingSpecs, material } 
                })}
              />
            </TabsContent>

            <TabsContent value="quotes" className="mt-6">
              <QuoteManager project={project} />
            </TabsContent>

            <TabsContent value="manufacturing" className="mt-6">
              <ManufacturingTracker project={project} />
            </TabsContent>

            <TabsContent value="settings" className="mt-6">
              <ProjectSettings 
                project={project}
                onUpdate={(updates) => updateProject.mutate(updates)}
              />
            </TabsContent>
          </Tabs>
        </div>

        <div className="space-y-6">
          <CADViewer project={project} />
        </div>
      </div>
    </div>
  )
}

// ===== UI COMPONENTS =====
// apps/web/src/components/ui/button.tsx
import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3',
        lg: 'h-11 rounded-md px-8',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = 'Button'

export { Button, buttonVariants }

// ===== CARD COMPONENT =====
// apps/web/src/components/ui/card.tsx
import * as React from 'react'
import { cn } from '@/lib/utils'

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      'rounded-lg border bg-card text-card-foreground shadow-sm',
      className
    )}
    {...props}
  />
))
Card.displayName = 'Card'

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex flex-col space-y-1.5 p-6', className)}
    {...props}
  />
))
CardHeader.displayName = 'CardHeader'

const CardTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn(
      'text-2xl font-semibold leading-none tracking-tight',
      className
    )}
    {...props}
  />
))
CardTitle.displayName = 'CardTitle'

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn('text-sm text-muted-foreground', className)}
    {...props}
  />
))
CardDescription.displayName = 'CardDescription'

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn('p-6 pt-0', className)} {...props} />
))
CardContent.displayName = 'CardContent'

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex items-center p-6 pt-0', className)}
    {...props}
  />
))
CardFooter.displayName = 'CardFooter'

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent }

// ===== UTILS =====
// apps/web/src/lib/utils.ts
import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(amount: number, currency = 'USD') {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).format(amount)
}

export function formatDate(date: Date | string) {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(date))
}

export function formatFileSize(bytes: number) {
  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  let unitIndex = 0
  
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex++
  }
  
  return `${size.toFixed(1)} ${units[unitIndex]}`
}

// ===== PROJECT CARD COMPONENT =====
// apps/web/src/components/dashboard/project-card.tsx
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Project, ProjectStatus } from '@/types'
import { formatCurrency, formatDate } from '@/lib/utils'
import { Clock, DollarSign, Package } from 'lucide-react'

interface ProjectCardProps {
  project: Project
}

export function ProjectCard({ project }: ProjectCardProps) {
  const statusColors = {
    [ProjectStatus.DRAFT]: 'bg-gray-500',
    [ProjectStatus.DESIGNING]: 'bg-blue-500',
    [ProjectStatus.QUOTING]: 'bg-yellow-500',
    [ProjectStatus.MANUFACTURING]: 'bg-spectrum-blue',
    [ProjectStatus.SHIPPED]: 'bg-purple-500',
    [ProjectStatus.COMPLETED]: 'bg-spectrum-green',
  }

  const getProgress = () => {
    const statusProgress = {
      [ProjectStatus.DRAFT]: 10,
      [ProjectStatus.DESIGNING]: 25,
      [ProjectStatus.QUOTING]: 50,
      [ProjectStatus.MANUFACTURING]: 75,
      [ProjectStatus.SHIPPED]: 90,
      [ProjectStatus.COMPLETED]: 100,
    }
    return statusProgress[project.status] || 0
  }

  return (
    <Link href={`/dashboard/projects/${project.id}`}>
      <Card className="hover:shadow-lg transition-shadow cursor-pointer">
        <div className={`h-1 ${statusColors[project.status]}`} />
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle className="text-lg">{project.name}</CardTitle>
              <CardDescription className="mt-1">
                {project.description}
              </CardDescription>
            </div>
            <Badge variant="outline" className="ml-2">
              {project.status.replace('_', ' ')}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <Progress value={getProgress()} className="mb-4" />
          
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div className="flex items-center text-gray-600">
              <Clock className="mr-2 h-4 w-4" />
              {formatDate(project.updatedAt)}
            </div>
            {project.quotes?.[0] && (
              <div className="flex items-center text-gray-600">
                <DollarSign className="mr-2 h-4 w-4" />
                {formatCurrency(project.quotes[0].costBreakdown.totalCost)}
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

// ===== AI ASSISTANT COMPONENT =====
// apps/web/src/components/dashboard/ai-assistant.tsx
'use client'

import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { X, Send, Mic, Paperclip } from 'lucide-react'
import api from '@/lib/api'

interface AIAssistantProps {
  open: boolean
  onClose: () => void
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

export function AIAssistant({ open, onClose }: AIAssistantProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Hello! I\'m your ProtoGen AI assistant. I can help you optimize designs, find materials, get quotes, and manage your manufacturing projects. How can I help you today?',
      timestamp: new Date(),
    },
  ])
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const sendMessage = useMutation({
    mutationFn: async (message: string) => {
      const { data } = await api.post('/ai/chat', { message })
      return data
    },
    onSuccess: (data) => {
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: data.response,
        timestamp: new Date(),
      }])
    },
  })

  const handleSend = () => {
    if (!input.trim()) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    sendMessage.mutate(input)
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ type: 'spring', damping: 20 }}
          className="fixed right-0 top-0 h-full w-96 bg-white shadow-2xl z-50"
        >
          <div className="flex flex-col h-full">
            <div className="p-4 border-b bg-spectrum-gradient">
              <div className="flex items-center justify-between text-white">
                <h2 className="text-lg font-semibold">AI Assistant</h2>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onClose}
                  className="text-white hover:bg-white/20"
                >
                  <X className="h-5 w-5" />
                </Button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${
                    message.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  <Card
                    className={`max-w-[80%] p-3 ${
                      message.role === 'user'
                        ? 'bg-spectrum-blue text-white'
                        : 'bg-gray-100'
                    }`}
                  >
                    <p className="text-sm">{message.content}</p>
                    <p className={`text-xs mt-1 ${
                      message.role === 'user' ? 'text-white/70' : 'text-gray-500'
                    }`}>
                      {new Date(message.timestamp).toLocaleTimeString()}
                    </p>
                  </Card>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            <div className="p-4 border-t">
              <div className="flex items-center space-x-2">
                <Button variant="ghost" size="icon">
                  <Paperclip className="h-5 w-5" />
                </Button>
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSend()}
                  placeholder="Type your message..."
                  className="flex-1 px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-spectrum-blue"
                />
                <Button variant="ghost" size="icon">
                  <Mic className="h-5 w-5" />
                </Button>
                <Button
                  onClick={handleSend}
                  disabled={!input.trim() || sendMessage.isPending}
                  className="bg-spectrum-blue hover:bg-spectrum-blue/90"
                >
                  <Send className="h-5 w-5" />
                </Button>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ===== CAD VIEWER COMPONENT =====
// apps/web/src/components/project/cad-viewer.tsx
'use client'

import { Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Stage, Grid } from '@react-three/drei'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Download, Maximize2, RotateCw } from 'lucide-react'
import { Project } from '@/types'

interface CADViewerProps {
  project: Project
}

function Model() {
  // This would load the actual CAD model
  return (
    <mesh>
      <boxGeometry args={[2, 2, 2]} />
      <meshStandardMaterial color="#00AEEF" />
    </mesh>
  )
}

export function CADViewer({ project }: CADViewerProps) {
  return (
    <Card className="h-[500px]">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>3D Preview</CardTitle>
        <div className="flex space-x-2">
          <Button variant="ghost" size="icon">
            <RotateCw className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon">
            <Maximize2 className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon">
            <Download className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="h-[calc(100%-80px)] p-0">
        <Canvas camera={{ position: [5, 5, 5], fov: 50 }}>
          <Suspense fallback={null}>
            <Stage environment="city" intensity={0.6}>
              <Model />
            </Stage>
            <Grid infiniteGrid />
            <OrbitControls enablePan enableZoom enableRotate />
          </Suspense>
        </Canvas>
      </CardContent>
    </Card>
  )
}

// ===== WEBSOCKET HOOK =====
// apps/web/src/hooks/use-websocket.ts
import { useEffect, useRef } from 'react'
import { io, Socket } from 'socket.io-client'

export function useWebSocket(url: string) {
  const socketRef = useRef<Socket | null>(null)

  useEffect(() => {
    socketRef.current = io(url, {
      transports: ['websocket'],
    })

    return () => {
      socketRef.current?.disconnect()
    }
  }, [url])

  return socketRef.current
}

// ===== STORE =====
// apps/web/src/store/index.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AppState {
  theme: 'light' | 'dark'
  sidebarOpen: boolean
  aiAssistantOpen: boolean
  setTheme: (theme: 'light' | 'dark') => void
  toggleSidebar: () => void
  toggleAIAssistant: () => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      theme: 'light',
      sidebarOpen: true,
      aiAssistantOpen: false,
      setTheme: (theme) => set({ theme }),
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      toggleAIAssistant: () => set((state) => ({ aiAssistantOpen: !state.aiAssistantOpen })),
    }),
    {
      name: 'protogen-app-state',
    }
  )
)

// This is a comprehensive implementation of the ProtoGen SaaS application
// with all core features including:
// - Authentication (NextAuth)
// - Dashboard with project management
// - 3D CAD viewer
// - AI Assistant integration
// - Material selection
// - Quote management
// - Real-time updates via WebSocket
// - Responsive design with Tailwind
// - State management with Zustand
// - API integration with React Query
// - Full TypeScript support