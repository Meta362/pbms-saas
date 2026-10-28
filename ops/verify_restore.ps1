param(
    [string]$BackupDir = "C:\Projects\pbms-saas\ops\backups",
    [string]$VerifyDbName = "pbms_restore_verify",
    [string]$DbUser = "postgres",
    [string]$DbHost = "127.0.0.1",
    [string]$DbPort = "5432"
)

$ErrorActionPreference = "Stop"

if (-not $env:PGPASSWORD) {
    $envPath = "C:\Projects\pbms-saas\backend\.env"
    if (Test-Path $envPath) {
        $match = Select-String -Path $envPath -Pattern "^POSTGRES_PASSWORD=(.*)$"
        if ($match) {
            $env:PGPASSWORD = $match.Matches[0].Groups[1].Value.Trim()
        }
    }
}

if (-not $env:PBMS_BACKUP_PASSPHRASE) {
    $env:PBMS_BACKUP_PASSPHRASE = "LocalDevOnly-Backup-Passphrase-ChangeInProd-2026"
}

$latestEncrypted = Get-ChildItem -Path $BackupDir -Filter "*.dump.enc" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $latestEncrypted) {
    throw "No encrypted backup files (*.dump.enc) found in $BackupDir"
}

$encryptedPath = $latestEncrypted.FullName
$checksumPath = "${encryptedPath}.sha256"
$tempDecryptedDump = Join-Path $BackupDir "temp_restore_verify.dump"

Write-Host "[1/5] Verifying SHA-256 checksum for $($latestEncrypted.Name)..." -ForegroundColor Cyan
$expectedHash = (Get-Content -Path $checksumPath -Raw).Trim()
$actualHash = (Get-FileHash -Path $encryptedPath -Algorithm SHA256).Hash
if ($expectedHash -ne $actualHash) {
    throw "Integrity check failed! Expected $expectedHash but got $actualHash"
}
Write-Host "  Checksum verified: $actualHash" -ForegroundColor Green

Write-Host "[2/5] Decrypting archive for verification drill..." -ForegroundColor Cyan
$allBytes = [System.IO.File]::ReadAllBytes($encryptedPath)
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
    Write-Host "[3/5] Recreating temporary verification database '$VerifyDbName'..." -ForegroundColor Cyan
    psql -U $DbUser -h $DbHost -p $DbPort -c "DROP DATABASE IF EXISTS $VerifyDbName;" | Out-Null
    psql -U $DbUser -h $DbHost -p $DbPort -c "CREATE DATABASE $VerifyDbName ENCODING 'UTF8';" | Out-Null

    Write-Host "[4/5] Restoring archive into '$VerifyDbName' via pg_restore..." -ForegroundColor Cyan
    pg_restore --host=$DbHost --port=$DbPort --username=$DbUser --dbname=$VerifyDbName --no-owner --no-acl "$tempDecryptedDump"
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore failed with exit code $LASTEXITCODE"
    }

    Write-Host "[5/5] Verifying restored data integrity in '$VerifyDbName'..." -ForegroundColor Cyan
    $usersCount = psql -U $DbUser -h $DbHost -p $DbPort -d $VerifyDbName -tAc "SELECT COUNT(*) FROM accounts_user;"
    $tenantsCount = psql -U $DbUser -h $DbHost -p $DbPort -d $VerifyDbName -tAc "SELECT COUNT(*) FROM tenants_tenant;"
    $ordersCount = psql -U $DbUser -h $DbHost -p $DbPort -d $VerifyDbName -tAc "SELECT COUNT(*) FROM operations_salesorder;"
    $auditsCount = psql -U $DbUser -h $DbHost -p $DbPort -d $VerifyDbName -tAc "SELECT COUNT(*) FROM core_auditevent;"

    Write-Host "RESTORE VERIFICATION DRILL PASSED:" -ForegroundColor Green
    Write-Host "  Restored Users        : $usersCount"
    Write-Host "  Restored Tenants      : $tenantsCount"
    Write-Host "  Restored Sales Orders : $ordersCount"
    Write-Host "  Restored Audit Events : $auditsCount"
} finally {
    if (Test-Path $tempDecryptedDump) {
        Remove-Item -Force $tempDecryptedDump
    }
    psql -U $DbUser -h $DbHost -p $DbPort -c "DROP DATABASE IF EXISTS $VerifyDbName;" | Out-Null
}
