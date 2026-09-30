# Windows MSI signing

The MSI metadata identifies the manufacturer as **Dexmond Technologies - Ireland**. A trusted Windows publisher name, however, comes from the subject of a real code-signing certificate. It cannot be created by changing application text or Tauri configuration.

## Prerequisite

Obtain an organization-validation or extended-validation code-signing certificate for the applicable Dexmond Technologies legal entity from a public CA. The certificate must:

- include the Code Signing enhanced key usage (`1.3.6.1.5.5.7.3.3`);
- have its private key available to the build identity, normally through `Cert:\CurrentUser\My`, a hardware token, or an approved cloud-signing service;
- have a subject whose verified organization is Dexmond Technologies and whose displayed geography/legal identity matches the certificate authority's validation;
- be protected and used according to Dexmond Technologies' release-key policy.

No certificate or private key belongs in this repository, `.env`, CI log, chat, or installer assets.

## Local signed build

After importing the certificate for the release account, list eligible certificates:

```powershell
Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
  Select-Object Subject, Thumbprint, NotAfter, HasPrivateKey
```

Then build and verify the MSI:

```powershell
.\scripts\build-signed-windows.ps1 -CertificateThumbprint "THE_SHA1_THUMBPRINT"
```

The script validates the private key, Code Signing usage, and Dexmond Technologies subject; gives Tauri only a temporary signing configuration; uses SHA-256 and a timestamp service; deletes the temporary configuration; and fails unless Windows reports a valid Authenticode signature on the produced MSI.

## Release verification

Independently verify the final artifact before distribution:

```powershell
Get-AuthenticodeSignature .\src-tauri\target\release\bundle\msi\agentSQL_0.0.1_x64_en-US.msi |
  Format-List Status, StatusMessage, Path, SignerCertificate, TimeStamperCertificate
```

The required outcome is `Status: Valid`, a Dexmond Technologies signer subject, and a valid timestamp. The installer should then be hashed, placed in the controlled release repository, and associated with the build provenance/SBOM. If a hardware token or cloud key vault is mandated, replace the certificate-store step with a reviewed Tauri `signCommand` integration; do not export the release private key merely to fit this script.

## Current repository status

The application is ready to consume a certificate thumbprint at release time, but the build machine currently has no Dexmond Technologies code-signing certificate with a private key installed. Therefore, a genuinely signed MSI cannot be produced until the certificate owner provisions that credential.
