param(
    [Parameter(Mandatory = $true)]
    [string]$CertificateThumbprint,
    [string]$TimestampUrl = "https://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$expectedPublisher = "Dexmond Technologies"
$normalizedThumbprint = ($CertificateThumbprint -replace "\s", "").ToUpperInvariant()
$certificate = Get-ChildItem -LiteralPath "Cert:\CurrentUser\My\$normalizedThumbprint" -ErrorAction Stop

if (-not $certificate.HasPrivateKey) {
    throw "The selected certificate has no accessible private key."
}
if ($certificate.Subject -notmatch [regex]::Escape($expectedPublisher)) {
    throw "Certificate subject '$($certificate.Subject)' does not identify Dexmond Technologies. Windows displays the certificate subject as the verified publisher; an MSI label cannot replace it."
}
$codeSigningEku = $certificate.EnhancedKeyUsageList | Where-Object { $_.ObjectId.Value -eq "1.3.6.1.5.5.7.3.3" }
if (-not $codeSigningEku) {
    throw "The selected certificate is not valid for code signing."
}

$signingConfig = @{
    bundle = @{
        windows = @{
            certificateThumbprint = $normalizedThumbprint
            digestAlgorithm = "sha256"
            timestampUrl = $TimestampUrl
        }
    }
} | ConvertTo-Json -Depth 5

$temporaryConfig = Join-Path $env:TEMP "agentsql-signing-$PID.json"
$repository = Split-Path $PSScriptRoot -Parent
try {
    Set-Content -LiteralPath $temporaryConfig -Value $signingConfig -Encoding UTF8
    Push-Location $repository
    & npm.cmd run tauri -- build --bundles msi --config $temporaryConfig
    if ($LASTEXITCODE -ne 0) { throw "The MSI build or signing step failed with exit code $LASTEXITCODE." }

    $installers = Get-ChildItem -Path "src-tauri\target\release\bundle\msi\*.msi" -File
    if (-not $installers) { throw "No MSI was produced." }
    foreach ($installer in $installers) {
        $signature = Get-AuthenticodeSignature -LiteralPath $installer.FullName
        if ($signature.Status -ne "Valid") {
            throw "Signature verification failed for $($installer.Name): $($signature.Status) $($signature.StatusMessage)"
        }
        Write-Host "Verified signed installer: $($installer.FullName)"
        Write-Host "Signer: $($signature.SignerCertificate.Subject)"
    }
}
finally {
    Pop-Location -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temporaryConfig -Force -ErrorAction SilentlyContinue
}
