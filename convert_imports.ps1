# Script to convert relative imports to absolute imports
# Run from Bot directory

$ErrorActionPreference = "Stop"

Write-Host "🔄 Converting relative imports to absolute imports..." -ForegroundColor Cyan

# Define conversion mappings (from relative to absolute)
$conversions = @{
    # Two-level parent imports (..)
    'from \.\.interfaces import' = 'from src.interfaces import'
    'from \.\.exceptions import' = 'from src.exceptions import'
    'from \.\.core\.logging_config import' = 'from src.core.logging_config import'
    'from \.\. import' = 'from src import'
    'from \.\.constants import' = 'from src.constants import'
    'from \.\.risk\.martingale_validator import' = 'from src.risk.martingale_validator import'
    'from \.\.domain\.position_lifecycle_service import' = 'from src.domain.position_lifecycle_service import'
    'from \.\.domain import' = 'from src.domain import'
    'from \.\.domain\.errors import' = 'from src.domain.errors import'
    'from \.\.risk\.risk_envelope_calculator import' = 'from src.risk.risk_envelope_calculator import'
    'from \.\.utils\.decorators import' = 'from src.utils.decorators import'
    'from \.\.core\.configuration import' = 'from src.core.configuration import'
    
    # Three-level parent imports (...) - for components in subdirectories
    'from \.\.\.interfaces import' = 'from src.interfaces import'
    'from \.\.\.risk\.martingale_validator import' = 'from src.risk.martingale_validator import'
    
    # Same-level imports (.) - convert to absolute within module
    # These need context-aware replacement, handled separately
}

# Get all Python files in src directory
$pythonFiles = Get-ChildItem -Path "src" -Filter "*.py" -Recurse

$filesModified = 0
$totalReplacements = 0

foreach ($file in $pythonFiles) {
    $content = Get-Content -Path $file.FullName -Raw
    $originalContent = $content
    $fileReplacements = 0
    
    # Apply all conversion patterns
    foreach ($pattern in $conversions.Keys) {
        $replacement = $conversions[$pattern]
        if ($content -match $pattern) {
            $content = $content -replace $pattern, $replacement
            $matches = [regex]::Matches($originalContent, $pattern)
            $fileReplacements += $matches.Count
        }
    }
    
    # Handle same-level imports based on file location
    $relativePath = $file.DirectoryName -replace [regex]::Escape($PWD.Path + "\src\"), ""
    $modulePath = "src." + ($relativePath -replace "\\", ".")
    
    # Convert single dot imports to absolute
    if ($content -match 'from \. import') {
        $content = $content -replace 'from \. import', "from $modulePath import"
        $fileReplacements++
    }
    
    # Convert single dot module imports (e.g., from .signal_processor import)
    # Need to extract module name and convert properly
    $singleDotPattern = 'from \.(\w+) import'
    if ($content -match $singleDotPattern) {
        $content = $content -replace $singleDotPattern, "from $modulePath.`$1 import"
        $matches = [regex]::Matches($content, $singleDotPattern)
        $fileReplacements += $matches.Count
    }
    
    # Handle relative imports within strategies (e.g., from .position_state import)
    if ($file.DirectoryName -like "*\strategies*") {
        $content = $content -replace 'from \.position_state import', 'from src.strategies.position_state import'
        $content = $content -replace 'from \.entry_executor import', 'from src.strategies.entry_executor import'
        $content = $content -replace 'from \.dca_planner import', 'from src.strategies.dca_planner import'
        $content = $content -replace 'from \.trailing_manager import', 'from src.strategies.trailing_manager import'
        $content = $content -replace 'from \.phase_manager import', 'from src.strategies.phase_manager import'
        $content = $content -replace 'from \.support_calculator import', 'from src.strategies.support_calculator import'
        $content = $content -replace 'from \.position_bootstrapper import', 'from src.strategies.position_bootstrapper import'
        $content = $content -replace 'from \.\.support_calculator import', 'from src.strategies.support_calculator import'
        $content = $content -replace 'from \.base_strategy import', 'from src.strategies.base_strategy import'
        $content = $content -replace 'from \.trailing_profit import', 'from src.strategies.trailing_profit import'
    }
    
    # Handle signals module
    if ($file.DirectoryName -like "*\signals*") {
        $content = $content -replace 'from \.signal_processor import', 'from src.signals.signal_processor import'
        $content = $content -replace 'from \.webhook_handlers import', 'from src.signals.webhook_handlers import'
        $content = $content -replace 'from \.monitoring_router import', 'from src.signals.monitoring_router import'
        $content = $content -replace 'from \.signal_listener import', 'from src.signals.signal_listener import'
    }
    
    # Handle commands module
    if ($file.DirectoryName -like "*\commands*") {
        $content = $content -replace 'from \.base_command import', 'from src.commands.base_command import'
        $content = $content -replace 'from \.order_commands import', 'from src.commands.order_commands import'
        $content = $content -replace 'from \.command_history import', 'from src.commands.command_history import'
    }
    
    # Handle events module
    if ($file.DirectoryName -like "*\events*") {
        $content = $content -replace 'from \.event_bus import', 'from src.events.event_bus import'
        $content = $content -replace 'from \.trading_events import', 'from src.events.trading_events import'
    }
    
    # Handle cache module
    if ($file.DirectoryName -like "*\cache*") {
        $content = $content -replace 'from \.redis_cache import', 'from src.cache.redis_cache import'
        $content = $content -replace 'from \.cached_market_data import', 'from src.cache.cached_market_data import'
    }
    
    # Handle domain module
    if ($file.DirectoryName -like "*\domain*") {
        $content = $content -replace 'from \.decision_context import', 'from src.domain.decision_context import'
        $content = $content -replace 'from \.risk_decision import', 'from src.domain.risk_decision import'
    }
    
    # Handle confidence module
    if ($file.DirectoryName -like "*\confidence*") {
        $content = $content -replace 'from \.confidence_factor import', 'from src.strategies.confidence.confidence_factor import'
        $content = $content -replace 'from \.confidence_pipeline import', 'from src.strategies.confidence.confidence_pipeline import'
        $content = $content -replace 'from \.factors import', 'from src.strategies.confidence.factors import'
    }
    
    # Handle market_data module
    if ($file.DirectoryName -like "*\market_data*") {
        $content = $content -replace 'from \.circuit_breaker import', 'from src.market_data.circuit_breaker import'
    }
    
    # Handle components module
    if ($file.DirectoryName -like "*\components*") {
        $content = $content -replace 'from \.price_context_service import', 'from src.strategies.components.price_context_service import'
        $content = $content -replace 'from \.dca_level_selector import', 'from src.strategies.components.dca_level_selector import'
        $content = $content -replace 'from \.position_adjustment_planner import', 'from src.strategies.components.position_adjustment_planner import'
    }
    
    # Handle validation module
    if ($file.DirectoryName -like "*\validation*") {
        $content = $content -replace 'from \.startup_validation_service import', 'from src.validation.startup_validation_service import'
    }
    
    # Handle data module
    if ($file.DirectoryName -like "*\data*") {
        $content = $content -replace 'from \.market_data import', 'from src.data.market_data import'
    }
    
    # Handle trading module
    if ($file.DirectoryName -like "*\trading*") {
        $content = $content -replace 'from \.order_manager import', 'from src.trading.order_manager import'
    }
    
    # Handle position module
    if ($file.DirectoryName -like "*\position*") {
        $content = $content -replace 'from \.position_manager import', 'from src.position.position_manager import'
    }
    
    # Handle core module
    if ($file.DirectoryName -like "*\core*") {
        $content = $content -replace 'from \.configuration import', 'from src.core.configuration import'
        $content = $content -replace 'from \.logging_config import', 'from src.core.logging_config import'
    }
    
    # Handle database module
    if ($file.DirectoryName -like "*\database*") {
        $content = $content -replace 'from \.database_manager import', 'from src.database.database_manager import'
    }
    
    # Handle risk module
    if ($file.DirectoryName -like "*\risk*") {
        $content = $content -replace 'from \.risk_manager import', 'from src.risk.risk_manager import'
    }
    
    # Handle utils module
    if ($file.DirectoryName -like "*\utils*") {
        $content = $content -replace 'from \.ngrok_manager import', 'from src.utils.ngrok_manager import'
    }
    
    # Write back if changed
    if ($content -ne $originalContent) {
        Set-Content -Path $file.FullName -Value $content -NoNewline
        $filesModified++
        $totalReplacements += $fileReplacements
        Write-Host "✓ Modified: $($file.Name) ($fileReplacements replacements)" -ForegroundColor Green
    }
}

Write-Host "`n✅ Import conversion complete!" -ForegroundColor Green
Write-Host "Files modified: $filesModified" -ForegroundColor Cyan
Write-Host "Total replacements: $totalReplacements" -ForegroundColor Cyan
Write-Host "`nℹ️  Next step: Run compilation to verify all imports work correctly" -ForegroundColor Yellow
Write-Host "python -m compileall src -q" -ForegroundColor Gray
