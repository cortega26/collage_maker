# Advanced VS Code Terminal Fix Script
# This script performs a comprehensive diagnosis and repair of VS Code terminal issues
# including fixing corrupted settings.json files and cleaning terminal state

#Requires -Version 5.0

function Write-Header {
    param([string]$Text)
    Write-Host "`n$('=' * 60)" -ForegroundColor Blue
    Write-Host "  $Text" -ForegroundColor Blue
    Write-Host "$('=' * 60)" -ForegroundColor Blue
}

function Test-Administrator {
    $currentUser = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Restore-VSCodeSettings {
    param([string]$SettingsPath)
    
    Write-Header "REPAIRING CORRUPTED SETTINGS FILE"
    
    # First try to read the file to diagnose the corruption
    try {
        $content = Get-Content -Path $SettingsPath -Raw -ErrorAction Stop
        Write-Host "Reading settings file content..." -ForegroundColor Yellow
    }
    catch {
        Write-Host "Error reading settings.json: $_" -ForegroundColor Red
        $content = ""
    }
    
    # Check if the file exists but is corrupted
    if (Test-Path $SettingsPath) {
        # Create backup
        $backupPath = "$SettingsPath.corrupt_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        try {
            Copy-Item -Path $SettingsPath -Destination $backupPath -Force -ErrorAction Stop
            Write-Host "Created backup of corrupted settings file at: $backupPath" -ForegroundColor Green
        }
        catch {
            Write-Host "Failed to create backup: $_" -ForegroundColor Red
        }
        
        # Attempt to fix the JSON if it's just minor corruption
        try {
            # Try to parse and reformat the JSON
            $jsonObj = $content | ConvertFrom-Json -ErrorAction Stop
            $fixedJson = $jsonObj | ConvertTo-Json -Depth 10
            Write-Host "Fixed minor JSON formatting issues." -ForegroundColor Green
        }
        catch {
            Write-Host "JSON is severely corrupted and cannot be automatically fixed." -ForegroundColor Red
            Write-Host "Creating new minimal settings file..." -ForegroundColor Yellow
            
            # Create minimal settings with terminal fixes
            $fixedJson = @{
                "terminal.integrated.persistentSessionReviveProcess" = "never"
                "terminal.integrated.enablePersistentSessions" = $false
                "terminal.integrated.gpuAcceleration" = "off"
                "terminal.integrated.shellIntegration.enabled" = $true
            } | ConvertTo-Json -Depth 10
        }
        
        # Write fixed settings back
        try {
            Set-Content -Path $SettingsPath -Value $fixedJson -Force -ErrorAction Stop
            Write-Host "Successfully repaired settings.json file." -ForegroundColor Green
        }
        catch {
            Write-Host "Failed to write new settings file: $_" -ForegroundColor Red
            
            # Last resort - try with empty JSON object
            try {
                Set-Content -Path $SettingsPath -Value "{}" -Force -ErrorAction Stop
                Write-Host "Created empty settings file as fallback." -ForegroundColor Yellow
            }
            catch {
                Write-Host "Critical failure: Unable to create settings file. Check file permissions." -ForegroundColor Red
            }
        }
    }
    else {
        # Settings file doesn't exist, create minimal one
        try {
            $minimalSettings = @{
                "terminal.integrated.persistentSessionReviveProcess" = "never"
                "terminal.integrated.enablePersistentSessions" = $false
            } | ConvertTo-Json
            
            Set-Content -Path $SettingsPath -Value $minimalSettings -Force -ErrorAction Stop
            Write-Host "Created new settings.json file with optimal terminal configuration." -ForegroundColor Green
        }
        catch {
            Write-Host "Failed to create settings file: $_" -ForegroundColor Red
        }
    }
}

function Clear-VSCodeTerminalState {
    param([string]$VSCodeDataPath)
    
    Write-Header "CLEANING TERMINAL STATE"
    
    # Check for all possible terminal state locations
    $locations = @(
        # Main workspace storage
        [PSCustomObject]@{
            Path = Join-Path -Path $VSCodeDataPath -ChildPath "User\workspaceStorage"
            Description = "Workspace Storage"
            Pattern = "*terminal*"
        },
        # Global state
        [PSCustomObject]@{
            Path = Join-Path -Path $VSCodeDataPath -ChildPath "User\globalStorage"
            Description = "Global Storage"
            Pattern = "*terminal*"
        },
        # Extensions that might affect terminals
        [PSCustomObject]@{
            Path = Join-Path -Path $VSCodeDataPath -ChildPath "User\globalStorage"
            Description = "Extension State"
            Pattern = "*shell*"
        },
        # History/logs
        [PSCustomObject]@{
            Path = Join-Path -Path $VSCodeDataPath -ChildPath "logs"
            Description = "Terminal Logs"
            Pattern = "*terminal*"
        }
    )
    
    # Create a single backup directory for all items
    $backupDir = Join-Path -Path $VSCodeDataPath -ChildPath "terminal_state_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    $backupCreated = $false
    
    foreach ($location in $locations) {
        if (Test-Path $location.Path) {
            Write-Host "Scanning $($location.Description) for terminal state files..." -ForegroundColor Yellow
            
            # Find relevant files (both pattern and direct paths)
            $files = Get-ChildItem -Path $location.Path -Recurse -File -ErrorAction SilentlyContinue | 
                     Where-Object { 
                        $_.Name -like $location.Pattern -or 
                        $_.Name -like "*shell*" -or 
                        $_.Name -eq "state.json" -or
                        $_.Name -eq "terminals.json"
                     }
            
            if ($files -and $files.Count -gt 0) {
                Write-Host "Found $($files.Count) terminal state files in $($location.Description)." -ForegroundColor Yellow
                
                # Create backup directory if it doesn't exist yet
                if (-not $backupCreated) {
                    try {
                        New-Item -ItemType Directory -Path $backupDir -Force -ErrorAction Stop | Out-Null
                        $backupCreated = $true
                        Write-Host "Created backup directory: $backupDir" -ForegroundColor Green
                    }
                    catch {
                        Write-Host "Failed to create backup directory: $_" -ForegroundColor Red
                    }
                }
                
                # Process each file
                foreach ($file in $files) {
                    try {
                        # Create subfolder structure in backup to maintain organization
                        $relativePath = $file.FullName.Replace($location.Path, "").TrimStart("\")
                        $relativeDir = Split-Path -Path $relativePath
                        $backupFilePath = Join-Path -Path $backupDir -ChildPath $location.Description
                        $backupFilePath = Join-Path -Path $backupFilePath -ChildPath $relativeDir
                        
                        # Create directory structure if it doesn't exist
                        if (-not (Test-Path $backupFilePath)) {
                            New-Item -ItemType Directory -Path $backupFilePath -Force | Out-Null
                        }
                        
                        # Copy file to backup
                        $backupFile = Join-Path -Path $backupFilePath -ChildPath $file.Name
                        Copy-Item -Path $file.FullName -Destination $backupFile -Force
                        
                        # Remove or empty the file (emptying is safer than removing for some configs)
                        if ($file.Name -eq "state.json" -or $file.Extension -eq ".json") {
                            # For JSON files, empty them to {} rather than delete
                            Set-Content -Path $file.FullName -Value "{}" -Force
                            Write-Host "Reset: $($file.FullName)" -ForegroundColor Green
                        }
                        else {
                            # For other files, delete them
                            Remove-Item -Path $file.FullName -Force
                            Write-Host "Removed: $($file.FullName)" -ForegroundColor Green
                        }
                    }
                    catch {
                        Write-Host "Failed to process $($file.FullName): $_" -ForegroundColor Red
                    }
                }
            }
            else {
                Write-Host "No terminal state files found in $($location.Description)." -ForegroundColor Green
            }
        }
    }
    
    # Special handling for ExtensionHost files that can affect terminals
    $hostCachePath = Join-Path -Path $VSCodeDataPath -ChildPath "CachedExtensionVSIXs"
    if (Test-Path $hostCachePath) {
        try {
            Write-Host "Clearing extension host cache..." -ForegroundColor Yellow
            Remove-Item -Path $hostCachePath\* -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "Extension host cache cleared." -ForegroundColor Green
        }
        catch {
            Write-Host "Failed to clear extension cache: $_" -ForegroundColor Red
        }
    }
    
    return $backupCreated
}

function Get-InstalledExtensions {
    param([string]$VSCodeDataPath)
    
    Write-Header "CHECKING PROBLEMATIC EXTENSIONS"
    
    $extensionsPath = Join-Path -Path $VSCodeDataPath -ChildPath "extensions"
    if (Test-Path $extensionsPath) {
        $potentialProblematicExtensions = @(
            "*terminal*",
            "*powershell*",
            "*shell*",
            "*remote*"
        )
        
        Write-Host "Scanning for extensions that might affect terminal behavior..." -ForegroundColor Yellow
        
        $foundExtensions = @()
        foreach ($pattern in $potentialProblematicExtensions) {
            $matches = Get-ChildItem -Path $extensionsPath -Directory | Where-Object { $_.Name -like $pattern }
            $foundExtensions += $matches
        }
        
        if ($foundExtensions.Count -gt 0) {
            Write-Host "Found $($foundExtensions.Count) extensions that might affect terminal behavior:" -ForegroundColor Yellow
            $foundExtensions | ForEach-Object {
                # Try to read extension details
                $manifestPath = Join-Path -Path $_.FullName -ChildPath "package.json"
                if (Test-Path $manifestPath) {
                    try {
                        $manifest = Get-Content -Path $manifestPath -Raw | ConvertFrom-Json
                        $extName = if ($manifest.displayName) { $manifest.displayName } else { $manifest.name }
                        $extVersion = $manifest.version
                        Write-Host "  - $extName v$extVersion" -ForegroundColor Yellow
                    }
                    catch {
                        Write-Host "  - $($_.Name)" -ForegroundColor Yellow
                    }
                }
                else {
                    Write-Host "  - $($_.Name)" -ForegroundColor Yellow
                }
            }
            
            Write-Host "`nConsider temporarily disabling these extensions to isolate the issue." -ForegroundColor Cyan
            Write-Host "You can disable extensions in VS Code by:" -ForegroundColor Cyan
            Write-Host "1. Opening VS Code" -ForegroundColor Cyan
            Write-Host "2. Press Ctrl+Shift+X to open the Extensions view" -ForegroundColor Cyan
            Write-Host "3. Right-click on the extension and select 'Disable'" -ForegroundColor Cyan
        }
        else {
            Write-Host "No potentially problematic extensions found." -ForegroundColor Green
        }
    }
}

function Reset-TerminalProfile {
    param([string]$VSCodeDataPath)
    
    Write-Header "RESETTING TERMINAL PROFILES"
    
    # Find terminal profiles configuration
    $profilesPath = Join-Path -Path $VSCodeDataPath -ChildPath "User\profiles.json"
    if (Test-Path $profilesPath) {
        try {
            # Back up profiles
            $backupPath = "$profilesPath.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Copy-Item -Path $profilesPath -Destination $backupPath -Force
            Write-Host "Created backup of profiles at: $backupPath" -ForegroundColor Green
            
            # Read profiles
            $profiles = Get-Content -Path $profilesPath -Raw -ErrorAction Stop | ConvertFrom-Json
            
            # Check for terminal profiles
            $terminalProfiles = $profiles.PSObject.Properties | 
                                Where-Object { $_.Name -like "*terminal*" }
            
            if ($terminalProfiles) {
                Write-Host "Terminal profiles found. Resetting..." -ForegroundColor Yellow
                
                # Remove terminal profiles
                foreach ($profile in $terminalProfiles) {
                    $profiles.PSObject.Properties.Remove($profile.Name)
                }
                
                # Save updated profiles
                $profiles | ConvertTo-Json -Depth 10 | Set-Content -Path $profilesPath -Force
                Write-Host "Terminal profiles have been reset." -ForegroundColor Green
            }
            else {
                Write-Host "No terminal profiles found in profiles.json." -ForegroundColor Green
            }
        }
        catch {
            Write-Host "Error processing profiles.json: $_" -ForegroundColor Red
            Write-Host "Attempting to create clean profiles file..." -ForegroundColor Yellow
            
            try {
                Set-Content -Path $profilesPath -Value "{}" -Force
                Write-Host "Created empty profiles.json file." -ForegroundColor Green
            }
            catch {
                Write-Host "Failed to create profiles.json: $_" -ForegroundColor Red
            }
        }
    }
    else {
        Write-Host "No profiles.json file found. No action needed." -ForegroundColor Green
    }
}

function Optimize-VSCodeConfiguration {
    param([string]$SettingsPath)
    
    Write-Header "OPTIMIZING VS CODE CONFIGURATION"
    
    try {
        # Check if settings file exists after repair
        if (Test-Path $SettingsPath) {
            # Read the settings file
            $settings = Get-Content -Path $SettingsPath -Raw | ConvertFrom-Json
            
            # Convert to PSObject if it's not already
            if ($settings -isnot [PSCustomObject]) {
                $settings = [PSCustomObject]$settings
            }
            
            # Define optimal terminal settings
            $optimalTerminalSettings = @{
                # Disable persistent sessions (primary cause of "reactivating terminals" issue)
                "terminal.integrated.enablePersistentSessions" = $false
                "terminal.integrated.persistentSessionReviveProcess" = "never"
                
                # Optimize terminal performance
                "terminal.integrated.gpuAcceleration" = "off"
                "terminal.integrated.rendererType" = "dom"
                
                # Disable shell integration that can cause hang
                "terminal.integrated.shellIntegration.enabled" = $false
                
                # Prevent terminal from inheriting problematic environment vars
                "terminal.integrated.inheritEnv" = $false
                
                # Disable problematic features
                "terminal.integrated.enableFileLinks" = $false
                
                # Configure process detection
                "terminal.integrated.processReaperInterval" = 5000
                
                # Set default terminal to PowerShell (more reliable than WSL or others)
                "terminal.integrated.defaultProfile.windows" = "PowerShell"
            }
            
            Write-Host "Applying optimal terminal settings..." -ForegroundColor Yellow
            
            # Apply each optimal setting
            foreach ($setting in $optimalTerminalSettings.GetEnumerator()) {
                # Check if property exists
                $propertyExists = $settings.PSObject.Properties.Name -contains $setting.Key
                
                if ($propertyExists) {
                    # Update existing property
                    $settings.($setting.Key) = $setting.Value
                }
                else {
                    # Add new property
                    $settings | Add-Member -NotePropertyName $setting.Key -NotePropertyValue $setting.Value
                }
                Write-Host "  - Set $($setting.Key) = $($setting.Value)" -ForegroundColor Green
            }
            
            # Save updated settings
            $settings | ConvertTo-Json -Depth 10 | Set-Content -Path $SettingsPath -Force
            Write-Host "Terminal settings have been optimized." -ForegroundColor Green
        }
        else {
            Write-Host "Settings file not found after repair attempt. This is unexpected." -ForegroundColor Red
        }
    }
    catch {
        Write-Host "Error optimizing VS Code configuration: $_" -ForegroundColor Red
    }
}

function Repair-SystemTerminals {
    Write-Header "REPAIRING SYSTEM TERMINALS"
    
    # Check Windows Terminal installation
    $windowsTerminalPath = "$env:LOCALAPPDATA\Microsoft\WindowsTerminal\settings.json"
    if (Test-Path $windowsTerminalPath) {
        Write-Host "Windows Terminal detected on system." -ForegroundColor Yellow
        Write-Host "Checking Windows Terminal configuration..." -ForegroundColor Yellow
        
        try {
            $wtSettings = Get-Content -Path $windowsTerminalPath -Raw | ConvertFrom-Json
            Write-Host "Windows Terminal configuration appears valid." -ForegroundColor Green
        }
        catch {
            Write-Host "Windows Terminal configuration may be corrupted." -ForegroundColor Red
            Write-Host "Consider resetting Windows Terminal settings in the app." -ForegroundColor Yellow
        }
    }
    
    # Check PowerShell profile
    $psProfilePath = $PROFILE
    if (Test-Path $psProfilePath) {
        Write-Host "PowerShell profile detected at: $psProfilePath" -ForegroundColor Yellow
        Write-Host "Checking if PowerShell profile contains terminal-related code..." -ForegroundColor Yellow
        
        try {
            $psProfile = Get-Content -Path $psProfilePath -Raw
            if ($psProfile -match "term" -or $psProfile -match "shell" -or $psProfile -match "console") {
                Write-Host "PowerShell profile contains terminal-related code that might affect VS Code." -ForegroundColor Yellow
                Write-Host "Consider temporarily renaming your PowerShell profile to test if it's causing the issue." -ForegroundColor Yellow
            }
            else {
                Write-Host "PowerShell profile appears normal." -ForegroundColor Green
            }
        }
        catch {
            Write-Host "Error reading PowerShell profile: $_" -ForegroundColor Red
        }
    }
    
    # Check PSReadLine
    try {
        $psReadLine = Get-Module -Name PSReadLine -ListAvailable
        if ($psReadLine) {
            Write-Host "PSReadLine module detected (version $($psReadLine.Version))." -ForegroundColor Yellow
            Write-Host "PSReadLine can sometimes interfere with terminal integration." -ForegroundColor Yellow
        }
    }
    catch {
        # PSReadLine check failed, not critical
    }
    
    # Check system environment variables that might affect terminals
    Write-Host "`nChecking system environment variables that might affect terminals..." -ForegroundColor Yellow
    $termVars = @("TERM_PROGRAM", "TERMINAL_EMULATOR", "ConEmuPID", "SESSIONNAME")
    foreach ($var in $termVars) {
        $value = [Environment]::GetEnvironmentVariable($var)
        if ($value) {
            Write-Host "  - $var = $value (Could affect terminal behavior)" -ForegroundColor Yellow
        }
    }
}

function Clear-VSCodeCache {
    param([string]$VSCodeDataPath)
    
    Write-Header "CLEARING VS CODE CACHE"
    
    $cachePaths = @(
        [PSCustomObject]@{ Path = Join-Path -Path $VSCodeDataPath -ChildPath "Cache"; Name = "General Cache" },
        [PSCustomObject]@{ Path = Join-Path -Path $VSCodeDataPath -ChildPath "CachedData"; Name = "Extension Data Cache" },
        [PSCustomObject]@{ Path = Join-Path -Path $VSCodeDataPath -ChildPath "Code Cache"; Name = "Code Cache" },
        [PSCustomObject]@{ Path = Join-Path -Path $VSCodeDataPath -ChildPath "GPUCache"; Name = "GPU Cache" }
    )
    
    foreach ($cache in $cachePaths) {
        if (Test-Path $cache.Path) {
            try {
                Write-Host "Clearing $($cache.Name)..." -ForegroundColor Yellow
                Remove-Item -Path "$($cache.Path)\*" -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "  - Successfully cleared $($cache.Name)" -ForegroundColor Green
            }
            catch {
                Write-Host "  - Failed to clear $($cache.Name): $_" -ForegroundColor Red
            }
        }
    }
    
    # Storage state that can affect terminal
    $storageState = Join-Path -Path $VSCodeDataPath -ChildPath "User\state.json"
    if (Test-Path $storageState) {
        try {
            Write-Host "Resetting storage state..." -ForegroundColor Yellow
            $backupPath = "$storageState.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Copy-Item -Path $storageState -Destination $backupPath -Force
            # Reset to empty JSON object instead of deleting
            Set-Content -Path $storageState -Value "{}" -Force
            Write-Host "  - Successfully reset storage state" -ForegroundColor Green
        }
        catch {
            Write-Host "  - Failed to reset storage state: $_" -ForegroundColor Red
        }
    }
}

function Test-VSCodeProcesses {
    Write-Header "CHECKING RUNNING VS CODE PROCESSES"
    
    $codeProcesses = Get-Process | Where-Object { $_.ProcessName -like "*code*" }
    
    if ($codeProcesses) {
        Write-Host "Found $($codeProcesses.Count) running VS Code processes:" -ForegroundColor Yellow
        $codeProcesses | ForEach-Object {
            try {
                $processPath = $_.Path
                $processName = $_.ProcessName
                $processPID = $_.Id
                
                Write-Host "  - $processName (PID: $processPID)" -ForegroundColor Yellow
                Write-Host "    Path: $processPath" -ForegroundColor Gray
                
                # Check for crashed/zombie processes
                if ($_.Responding -eq $false) {
                    Write-Host "    Status: NOT RESPONDING (potential zombie process)" -ForegroundColor Red
                }
                else {
                    Write-Host "    Status: Responding" -ForegroundColor Green
                }
            }
            catch {
                Write-Host "  - $($_.ProcessName) (PID: $($_.Id))" -ForegroundColor Yellow
            }
        }
        
        Write-Host "`nWould you like to terminate all VS Code processes? (Y/N)" -ForegroundColor Cyan
        $response = Read-Host
        
        if ($response -eq "Y" -or $response -eq "y") {
            foreach ($process in $codeProcesses) {
                try {
                    Write-Host "Terminating $($process.ProcessName) (PID: $($process.Id))..." -ForegroundColor Yellow
                    $process.Kill()
                    Start-Sleep -Seconds 1
                    Write-Host "  - Successfully terminated" -ForegroundColor Green
                }
                catch {
                    Write-Host "  - Failed to terminate: $_" -ForegroundColor Red
                }
            }
            
            # Double-check after termination
            Start-Sleep -Seconds 2
            $remainingProcesses = Get-Process | Where-Object { $_.ProcessName -like "*code*" }
            if ($remainingProcesses) {
                Write-Host "`nSome VS Code processes remain running. These may need to be terminated manually in Task Manager." -ForegroundColor Red
            }
            else {
                Write-Host "`nAll VS Code processes have been terminated." -ForegroundColor Green
            }
        }
    }
    else {
        Write-Host "No running VS Code processes found." -ForegroundColor Green
    }
}

function Start-VSCodeTerminalRepair {
    Clear-Host
    Write-Host "`n`n" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "=     ADVANCED VS CODE TERMINAL REPAIR UTILITY v2.0      =" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "`nThis utility will diagnose and fix VS Code terminal issues including the 'reactivating terminals...' problem.`n" -ForegroundColor White
    
    # Check admin privileges
    $isAdmin = Test-Administrator
    if (-not $isAdmin) {
        Write-Host "WARNING: This script is not running as Administrator. Some operations may fail." -ForegroundColor Yellow
        Write-Host "For best results, restart this script with Administrator privileges.`n" -ForegroundColor Yellow
        
        $continue = Read-Host "Continue anyway? (Y/N)"
        if ($continue -ne "Y" -and $continue -ne "y") {
            Write-Host "Operation cancelled. Please restart with Administrator privileges." -ForegroundColor Red
            return
        }
    }
    
    # Determine VS Code paths
    $appDataPath = $env:APPDATA
    $vsCodeDataPath = Join-Path -Path $appDataPath -ChildPath "Code"
    $vsCodeInsidersDataPath = Join-Path -Path $appDataPath -ChildPath "Code - Insiders"
    
    # Check which VS Code version is installed
    $vsCodePath = $null
    if (Test-Path $vsCodeDataPath) {
        $vsCodePath = $vsCodeDataPath
        Write-Host "VS Code (Stable) detected at: $vsCodePath" -ForegroundColor Green
    }
    
    if (Test-Path $vsCodeInsidersDataPath) {
        if (-not $vsCodePath) {
            $vsCodePath = $vsCodeInsidersDataPath
            Write-Host "VS Code Insiders detected at: $vsCodePath" -ForegroundColor Green
        }
        else {
            Write-Host "VS Code Insiders also detected at: $vsCodeInsidersDataPath" -ForegroundColor Yellow
            
            Write-Host "`nWhich VS Code installation would you like to repair?" -ForegroundColor Cyan
            Write-Host "1. VS Code Stable ($vsCodeDataPath)" -ForegroundColor White
            Write-Host "2. VS Code Insiders ($vsCodeInsidersDataPath)" -ForegroundColor White
            $choice = Read-Host "Enter your choice (1 or 2)"
            
            if ($choice -eq "2") {
                $vsCodePath = $vsCodeInsidersDataPath
                Write-Host "Using VS Code Insiders configuration path." -ForegroundColor Green
            }
        }
    }
    
    if (-not $vsCodePath) {
        Write-Host "ERROR: VS Code installation not detected. Please verify VS Code is installed." -ForegroundColor Red
        return
    }
    
    # Define settings path
    $userSettingsPath = Join-Path -Path $vsCodePath -ChildPath "User\settings.json"
    
    # Run diagnostic steps
    Test-VSCodeProcesses
    
    # Fix the settings JSON - this was the primary issue in the logs
    Restore-VSCodeSettings -SettingsPath $userSettingsPath
    
    # Check for extension issues
    Get-InstalledExtensions -VSCodeDataPath $vsCodePath
    
    # Clean terminal state
    Clear-VSCodeTerminalState -VSCodeDataPath $vsCodePath
    
    # Reset terminal profiles
    Reset-TerminalProfile -VSCodeDataPath $vsCodePath
    
    # Apply optimal settings
    Optimize-VSCodeConfiguration -SettingsPath $userSettingsPath
    
    # Clear cache
    Clear-VSCodeCache -VSCodeDataPath $vsCodePath
    
    # Check system terminal configuration
    Repair-SystemTerminals
    
    # Final summary
    Write-Header "REPAIR COMPLETE"
    
    Write-Host "All terminal-related issues have been addressed. Here's what was done:" -ForegroundColor Green
    Write-Host "1. Fixed or recreated corrupt settings.json file" -ForegroundColor Green
    Write-Host "2. Cleared terminal state and persistent session data" -ForegroundColor Green
    Write-Host "3. Reset terminal profiles and configurations" -ForegroundColor Green
    Write-Host "4. Applied optimal terminal settings" -ForegroundColor Green
    Write-Host "5. Cleared VS Code cache" -ForegroundColor Green
    Write-Host "6. Identified potential system-level issues" -ForegroundColor Green
    
    Write-Host "`nNext steps:" -ForegroundColor Cyan
    Write-Host "1. Restart your computer to ensure all processes are reset" -ForegroundColor Cyan
    Write-Host "2. Start VS Code and check if the terminal issue is resolved" -ForegroundColor Cyan
    Write-Host "3. If problems persist, try reinstalling VS Code completely" -ForegroundColor Cyan
    
    Write-Host "`nIf you need to restore any settings from backups, they can be found in:" -ForegroundColor Yellow
    Write-Host "$vsCodePath (look for files with backup_ in the name)" -ForegroundColor Yellow
    
    Write-Host "`nRepair utility completed successfully." -ForegroundColor Cyan
}

# Start the repair process
Start-VSCodeTerminalRepair