/**
 * Combobox Component
 * 
 * A searchable dropdown component with filtering capabilities.
 * Built with Radix UI Popover and custom search input.
 * 
 * @module components/ui/combobox
 */

'use client'

import * as React from 'react'
import { Check, ChevronsUpDown, Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'

// ============================================================================
// Types
// ============================================================================

export interface ComboboxOption {
  value: string
  label: string
  description?: string
  icon?: React.ReactNode
  group?: string
}

interface ComboboxProps {
  options: ComboboxOption[]
  value: string
  onValueChange: (value: string) => void
  placeholder?: string
  searchPlaceholder?: string
  emptyMessage?: string
  disabled?: boolean
  className?: string
  /** Show loading state */
  loading?: boolean
  /** Allow custom value not in options */
  allowCustomValue?: boolean
}

// ============================================================================
// Combobox Component
// ============================================================================

export function Combobox({
  options,
  value,
  onValueChange,
  placeholder = 'Select option...',
  searchPlaceholder = 'Search...',
  emptyMessage = 'No results found.',
  disabled = false,
  className,
  loading = false,
  allowCustomValue = false,
}: ComboboxProps) {
  const [open, setOpen] = React.useState(false)
  const [search, setSearch] = React.useState('')
  const inputRef = React.useRef<HTMLInputElement>(null)

  // Filter options based on search
  const filteredOptions = React.useMemo(() => {
    if (!search) return options
    const searchLower = search.toLowerCase()
    return options.filter(
      (option) =>
        option.label.toLowerCase().includes(searchLower) ||
        option.value.toLowerCase().includes(searchLower) ||
        option.description?.toLowerCase().includes(searchLower)
    )
  }, [options, search])

  // Group options if groups are defined
  const groupedOptions = React.useMemo(() => {
    const groups: Record<string, ComboboxOption[]> = {}
    const ungrouped: ComboboxOption[] = []

    filteredOptions.forEach((option) => {
      if (option.group) {
        if (!groups[option.group]) {
          groups[option.group] = []
        }
        groups[option.group].push(option)
      } else {
        ungrouped.push(option)
      }
    })

    return { groups, ungrouped }
  }, [filteredOptions])

  // Get display label for current value
  const selectedOption = options.find((option) => option.value === value)
  const displayValue = selectedOption?.label || (allowCustomValue && value ? value : placeholder)

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && allowCustomValue && search && filteredOptions.length === 0) {
      onValueChange(search.toUpperCase())
      setOpen(false)
      setSearch('')
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={cn(
            'w-full justify-between font-normal',
            !value && 'text-muted-foreground',
            className
          )}
        >
          <span className="truncate flex items-center gap-2">
            {selectedOption?.icon}
            {displayValue}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        {/* Search Input */}
        <div className="flex items-center border-b px-3 py-2">
          <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
          <Input
            ref={inputRef}
            placeholder={searchPlaceholder}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleKeyDown}
            className="h-8 border-0 bg-transparent p-0 focus-visible:ring-0 focus-visible:ring-offset-0"
          />
          {search && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={() => setSearch('')}
            >
              <X className="h-3 w-3" />
            </Button>
          )}
        </div>

        {/* Options List */}
        <ScrollArea className="max-h-[300px]">
          {loading ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              Loading...
            </div>
          ) : filteredOptions.length === 0 ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              {allowCustomValue && search ? (
                <div>
                  <p>{emptyMessage}</p>
                  <p className="mt-1 text-xs">Press Enter to use "{search.toUpperCase()}"</p>
                </div>
              ) : (
                emptyMessage
              )}
            </div>
          ) : (
            <div className="p-1">
              {/* Ungrouped options */}
              {groupedOptions.ungrouped.map((option) => (
                <ComboboxItem
                  key={option.value}
                  option={option}
                  isSelected={value === option.value}
                  onSelect={() => {
                    onValueChange(option.value)
                    setOpen(false)
                    setSearch('')
                  }}
                />
              ))}

              {/* Grouped options */}
              {Object.entries(groupedOptions.groups).map(([group, groupOptions]) => (
                <div key={group}>
                  <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                    {group}
                  </div>
                  {groupOptions.map((option) => (
                    <ComboboxItem
                      key={option.value}
                      option={option}
                      isSelected={value === option.value}
                      onSelect={() => {
                        onValueChange(option.value)
                        setOpen(false)
                        setSearch('')
                      }}
                    />
                  ))}
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}

// ============================================================================
// Combobox Item
// ============================================================================

interface ComboboxItemProps {
  option: ComboboxOption
  isSelected: boolean
  onSelect: () => void
}

function ComboboxItem({ option, isSelected, onSelect }: ComboboxItemProps) {
  return (
    <button
      type="button"
      className={cn(
        'relative flex w-full cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none',
        'hover:bg-accent hover:text-accent-foreground',
        isSelected && 'bg-accent text-accent-foreground'
      )}
      onClick={onSelect}
    >
      <Check
        className={cn('mr-2 h-4 w-4', isSelected ? 'opacity-100' : 'opacity-0')}
      />
      <div className="flex flex-col items-start gap-0.5">
        <span className="flex items-center gap-2">
          {option.icon}
          {option.label}
        </span>
        {option.description && (
          <span className="text-xs text-muted-foreground">{option.description}</span>
        )}
      </div>
    </button>
  )
}

export default Combobox
