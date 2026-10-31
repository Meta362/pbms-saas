param(
    [string]$BackupDir = (Join-Path $PSScriptRoot "backups"),
    [string]$VerifyDbName = "pbms_restore_verify",
    [string]$DbUser = "postgres",
    [string]$DbHost = "127.0.0.1",
    [string]$DbPort = "5432"
)

$ErrorActionPreference = "Stop"

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
    throw "PBMS_BACKUP_PASSPHRASE environment variable is required for archive decryption. No insecure fallback permitted."
}

$latestEncrypted = Get-ChildItem -Path $BackupDir -Filter "*.dump.enc" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $latestEncrypted) {
    throw "No encrypted backup files (*.dump.enc) found in $BackupDir"
}

$encryptedPath = $latestEncrypted.FullName
$checksumPath = "${encryptedPath}.sha256"
$tempDecryptedDump = Join-Path $BackupDir "temp_restore_verify.dump"
$manifestFile = Join-Path $BackupDir "backup_manifest.json"

Write-Host "[1/6] Verifying SHA-256 checksum for $($latestEncrypted.Name)..." -ForegroundColor Cyan
if (-not (Test-Path $checksumPath)) {
    throw "Checksum file missing: $checksumPath"
}
$expectedHash = (Get-Content -Path $checksumPath -Raw).Trim()
$actualHash = (Get-FileHash -Path $encryptedPath -Algorithm SHA256).Hash
if ($expectedHash -ne $actualHash) {
    throw "Integrity check failed! Expected $expectedHash but got $actualHash"
}
Write-Host "  Checksum verified: $actualHash" -ForegroundColor Green

Write-Host "[2/6] Decrypting archive for verification drill..." -ForegroundColor Cyan
$allBytes = [System.IO.File]::ReadAllBytes($encryptedPath)
if ($allBytes.Length -lt 17) {
    throw "Archive file is truncated or corrupted (insufficient byte length)."
}
$salt = $allBytes[0..15]
$cipherBytes = $allBytes[16..($allBytes.Length - 1)]

$pbkdf2 = New-Object System.Security.Cryptography.Rfc2898DeriveBytes(
    $env:PBMS_BACKUP_PASSPHRASE,
    [byte[]]$salt,
    100000,
    [System.Security.Cryptography.HashAlgorithmName]::SHA256
)
$aes = [System.Security.Cryptography.Aes]::Create()
$aes.KeySize = 256
$aes.Key = $pbkdf2.GetBytes(32)
$aes.IV = $pbkdf2.GetBytes(16)

$decryptor = $aes.CreateDecryptor()
$plainBytes = $decryptor.TransformFinalBlock($cipherBytes, 0, $cipherBytes.Length)
[System.IO.File]::WriteAllBytes($tempDecryptedDump, $plainBytes)

try {
    Write-Host "[3/6] Inspecting archive catalog TOC via pg_restore --list..." -ForegroundColor Cyan
    $tocLines = pg_restore --list "$tempDecryptedDump"
    if ($LASTEXITCODE -ne 0 -or -not $tocLines) {
        throw "pg_restore --list failed or returned empty catalog TOC (exit code $LASTEXITCODE)."
    }
    Write-Host "  Catalog valid: $($tocLines.Count) TOC entries inspected." -ForegroundColor Green

    Write-Host "[4/6] Recreating temporary verification database '$VerifyDbName'..." -ForegroundColor Cyan
    psql -U $DbUser -h $DbHost -p $DbPort -c "DROP DATABASE IF EXISTS $VerifyDbName;" | Out-Null
    psql -U $DbUser -h $DbHost -p $DbPort -c "CREATE DATABASE $VerifyDbName ENCODING 'UTF8';" | Out-Null

    Write-Host "[5/6] Restoring archive into '$VerifyDbName' via pg_restore..." -ForegroundColor Cyan
    pg_restore --host=$DbHost --port=$DbPort --username=$DbUser --dbname=$VerifyDbName --no-owner --no-acl "$tempDecryptedDump"
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore failed with exit code $LASTEXITCODE"
    }

    Write-Host "[6/6] Verifying restored data counts and recording audit event..." -ForegroundColor Cyan
    $usersCount = [int](psql -U $DbUser -h $DbHost -p $DbPort -d $VerifyDbName -tAc "SELECT COUNT(*) FROM accounts_user;")
    $tenantsCount = [int](psql -U $DbUser -h $DbHost -p $DbPort -d $VerifyDbName -tAc "SELECT COUNT(*) FROM tenants_tenant;")
    $ordersCount = [int](psql -U $DbUser -h $DbHost -p $DbPort -d $VerifyDbName -tAc "SELECT COUNT(*) FROM operations_salesorder;")
    $auditsCount = [int](psql -U $DbUser -h $DbHost -p $DbPort -d $VerifyDbName -tAc "SELECT COUNT(*) FROM core_auditevent;")

    Write-Host "RESTORE VERIFICATION DRILL PASSED:" -ForegroundColor Green
    Write-Host "  Restored Users        : $usersCount"
    Write-Host "  Restored Tenants      : $tenantsCount"
    Write-Host "  Restored Sales Orders : $ordersCount"
    Write-Host "  Restored Audit Events : $auditsCount"

    # Update manifest file
    if (Test-Path $manifestFile) {
        try {
            $manifestJson = Get-Content -Path $manifestFile -Raw
            $manifestList = ConvertFrom-Json $manifestJson
            $archiveName = (Split-Path $encryptedPath -Leaf)
            foreach ($entry in $manifestList) {
                if ($entry.archive_file -eq $archiveName) {
                    $entry.verified = $true
                    $entry.verified_at = (Get-Date).ToUniversalTime().ToString("o")
                }
            }
            $manifestList | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestFile -Encoding UTF8
            Write-Host "  Manifest updated: verified status marked for $archiveName" -ForegroundColor Green
        } catch {
            Write-Warning "Failed to update backup manifest: $_"
        }
    }

    # Record BACKUP_RESTORE_VERIFIED in primary audit log via Django management command
    $backendDir = Join-Path $PSScriptRoot "..\backend"
    $pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = "python"
    }
    $managePy = Join-Path $backendDir "manage.py"
    if (Test-Path $managePy) {
        & $pythonExe $managePy record_backup_verified --archive "$($latestEncrypted.Name)" --sha256 "$actualHash" --users $usersCount --tenants $tenantsCount --orders $ordersCount --audits $auditsCount
    }
} finally {
    if (Test-Path $tempDecryptedDump) {
        Remove-Item -Force $tempDecryptedDump
    }
    psql -U $DbUser -h $DbHost -p $DbPort -c "DROP DATABASE IF EXISTS $VerifyDbName;" | Out-Null
}
