param(
    [string]$DbName = "pbms_dev",
    [string]$DbUser = "postgres",
    [string]$DbHost = "127.0.0.1",
    [string]$DbPort = "5432",
    [string]$BackupDir = "C:\Projects\pbms-saas\ops\backups"
)

$ErrorActionPreference = "Stop"

# Read PostgreSQL password from backend/.env if PGPASSWORD is not set
if (-not $env:PGPASSWORD) {
    $envPath = "C:\Projects\pbms-saas\backend\.env"
    if (Test-Path $envPath) {
        $match = Select-String -Path $envPath -Pattern "^POSTGRES_PASSWORD=(.*)$"
        if ($match) {
            $env:PGPASSWORD = $match.Matches[0].Groups[1].Value.Trim()
        }
    }
}

# Read or set local dev passphrase from environment variable (never hardcoded in production)
if (-not $env:PBMS_BACKUP_PASSPHRASE) {
    $env:PBMS_BACKUP_PASSPHRASE = "LocalDevOnly-Backup-Passphrase-ChangeInProd-2026"
}

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$rawDumpFile = Join-Path $BackupDir "${DbName}_${timestamp}.dump"
$encryptedFile = "${rawDumpFile}.enc"
$checksumFile = "${encryptedFile}.sha256"

Write-Host "[1/3] Running pg_dump (-Fc) for database '$DbName'..." -ForegroundColor Cyan
pg_dump --host=$DbHost --port=$DbPort --username=$DbUser --format=custom --no-owner --no-acl --file="$rawDumpFile" $DbName
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed with exit code $LASTEXITCODE"
}

Write-Host "[2/3] Encrypting backup archive with AES-256-CBC (PBKDF2)..." -ForegroundColor Cyan
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

Write-Host "[3/3] Computing SHA-256 integrity digest..." -ForegroundColor Cyan
$hashObj = Get-FileHash -Path $encryptedFile -Algorithm SHA256
$hashObj.Hash | Set-Content -Path $checksumFile -Encoding ASCII

Write-Host "BACKUP SUCCESSFUL:" -ForegroundColor Green
Write-Host "  Encrypted File : $encryptedFile"
Write-Host "  SHA-256 Digest : $($hashObj.Hash)"
