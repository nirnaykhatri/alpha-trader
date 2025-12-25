/**
 * Shared Trading Components Index
 * 
 * Re-exports all shared components for DCA bot configuration dialogs.
 * 
 * @module components/trading/shared
 */

// Form Components
export {
  SectionHeader,
  NumberStepper,
  MultiplierSlider,
  PercentInput,
  AmountInput,
  OrderTypeToggle,
  ToggleRow,
  type SectionHeaderProps,
  type NumberStepperProps,
  type MultiplierSliderProps,
  type PercentInputProps,
  type AmountInputProps,
  type OrderTypeToggleProps,
  type ToggleRowProps,
} from './dca-form-components'

// Form Sections
export {
  AveragingOrdersSection,
  PositionTpSlSection,
  RiskManagementSection,
  BotSettingsSection,
  type AveragingOrdersSectionProps,
  type PositionTpSlSectionProps,
  type RiskManagementSectionProps,
  type BotSettingsSectionProps,
} from './dca-form-sections'
