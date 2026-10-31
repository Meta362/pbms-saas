param(
    [string]$DbName = "pbms_dev",
    [string]$DbUser = "postgres",
    [string]$DbHost = "127.0.0.1",
    [string]$DbPort = "5432",
    [string]$BackupDir = (Join-Path $PSScriptRoot "backups"),
    [int]$RetentionDays = 30
)

$ErrorActionPreference = "Stop"

# Read PostgreSQL password from backend/.env if PGPASSWORD is not set
if (-not $env:PGPASSWORD) {
    $envPath = Join-Path $PSScriptRoot "..\backend\.env"
    if (Test-Path $envPath) {
        $match = Select-String -Path $envPath -Pattern "^POSTGRES_PASSWORD=(.*)$"
        if ($match) {
            $env:PGPASSWORD = $match.Matches[0].Groups[1].Value.Trim()
        }
    }
}

# Require PBMS_BACKUP_PASSPHRASE from environment; fail-closed without hardcoded fallback (SEC-002)
if (-not $env:PBMS_BACKUP_PASSPHRASE) {
    throw "PBMS_BACKUP_PASSPHRASE environment variable is required for backup encryption. No insecure fallback permitted."
}

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$rawDumpFile = Join-Path $BackupDir "${DbName}_${timestamp}.dump"
$encryptedFile = "${rawDumpFile}.enc"
$checksumFile = "${encryptedFile}.sha256"
$manifestFile = Join-Path $BackupDir "backup_manifest.json"

Write-Host "[1/4] Running pg_dump (-Fc) for database '$DbName'..." -ForegroundColor Cyan
pg_dump --host=$DbHost --port=$DbPort --username=$DbUser --format=custom --no-owner --no-acl --file="$rawDumpFile" $DbName
$dumpExitCode = $LASTEXITCODE
if ($dumpExitCode -ne 0) {
    throw "pg_dump failed with exit code $dumpExitCode"
}

$rawSizeBytes = (Get-Item $rawDumpFile).Length

Write-Host "[2/4] Encrypting backup archive with AES-256-CBC (PBKDF2)..." -ForegroundColor Cyan
$salt = New-Object byte[] 16
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($salt)
$pbkdf2 = New-Object System.Security.Cryptography.Rfc2898DeriveBytes(
    $env:PBMS_BACKUP_PASSPHRASE,
    $salt,
    100000,
    [System.Security.Cryptography.HashAlgorithmName]::SHA256
)
$aes = [System.Security.Cryptography.Aes]::Create()
$aes.KeySize = 256
$aes.Key = $pbkdf2.GetBytes(32)
$aes.IV = $pbkdf2.GetBytes(16)

$inBytes = [System.IO.File]::ReadAllBytes($rawDumpFile)
$encryptor = $aes.CreateEncryptor()
$cipherBytes = $encryptor.TransformFinalBlock($inBytes, 0, $inBytes.Length)

$outStream = [System.IO.File]::Create($encryptedFile)
try {
    $outStream.Write($salt, 0, $salt.Length)
    $outStream.Write($cipherBytes, 0, $cipherBytes.Length)
} finally {
    $outStream.Close()
}

# Remove unencrypted raw dump immediately
Remove-Item -Force $rawDumpFile
$encSizeBytes = (Get-Item $encryptedFile).Length

Write-Host "[3/4] Computing SHA-256 integrity digest..." -ForegroundColor Cyan
$hashObj = Get-FileHash -Path $encryptedFile -Algorithm SHA256
$hashObj.Hash | Set-Content -Path $checksumFile -Encoding ASCII

Write-Host "[4/4] Writing JSON manifest entry & applying retention policy..." -ForegroundColor Cyan
$manifestEntries = @()
if (Test-Path $manifestFile) {
    try {
        $rawJson = Get-Content -Path $manifestFile -Raw
        if ($rawJson.Trim()) {
            $manifestEntries = ConvertFrom-Json $rawJson
            if ($manifestEntries -isnot [array]) {
                $manifestEntries = @($manifestEntries)
            }
        }
    } catch {
        Write-Warning "Could not parse existing manifest file, reinitializing: $_"
        $manifestEntries = @()
    }
}

$newEntry = [ordered]@{
    timestamp_utc          = (Get-Date).ToUniversalTime().ToString("o")
    database               = $DbName
    archive_file           = (Split-Path $encryptedFile -Leaf)
    checksum_file          = (Split-Path $checksumFile -Leaf)
    raw_size_bytes         = $rawSizeBytes
    encrypted_size_bytes   = $encSizeBytes
    sha256_hash            = $hashObj.Hash
    encryption_algorithm   = "AES-256-CBC-PBKDF2-SHA256"
    pg_dump_exit_code      = $dumpExitCode
    status                 = "SUCCESS"
    verified               = $false
    verified_at            = $null
}

$manifestEntries += $newEntry
$manifestEntries | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestFile -Encoding UTF8

# Retention policy: Prune unverified/expired backups older than $RetentionDays (REQ-NFR-02)
if ($RetentionDays -gt 0) {
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    $prunedCount = 0
    Get-ChildItem -Path $BackupDir -File | Where-Object {
        $_.Name -ne "backup_manifest.json" -and $_.LastWriteTime -lt $cutoff
    } | ForEach-Object {
        Remove-Item -Force $_.FullName
        $prunedCount++
    }
    if ($prunedCount -gt 0) {
        Write-Host "  Retention pruning: removed $prunedCount expired backup artifact(s)." -ForegroundColor Yellow
    }
}

Write-Host "BACKUP SUCCESSFUL:" -ForegroundColor Green
Write-Host "  Encrypted File : $encryptedFile ($encSizeBytes bytes)"
Write-Host "  SHA-256 Digest : $($hashObj.Hash)"
Write-Host "  Manifest Entry : $manifestFile"
