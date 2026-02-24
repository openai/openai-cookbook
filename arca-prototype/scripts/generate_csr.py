#!/usr/bin/env python3
"""
Generate CSR (Certificate Signing Request) for AFIP WSASS.

The CSR must include SerialNumber=CUIT nnnnnnnnnnn (11-digit CUIT) in the subject.
Upload the generated .csr to WSASS (https://auth.afip.gob.ar/contribuyente_/login.xhtml),
download the certificate, and associate it with veconsumerws.

Usage:
    python scripts/generate_csr.py [CUIT] [output_dir]
    # Or with env: ARCA_CUIT=20268448536 python scripts/generate_csr.py

Output:
    - {output_dir}/arca_private.key  (private key, keep secret)
    - {output_dir}/arca_request.csr  (upload to WSASS)
"""
import os
import sys
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError:
    print("Install cryptography: pip install cryptography")
    sys.exit(1)


def generate_csr(cuit: str, output_dir: Path) -> tuple[Path, Path]:
    """
    Generate private key and CSR for AFIP WSASS.

    Args:
        cuit: 11-digit CUIT (will be normalized)
        output_dir: Directory for .key and .csr files

    Returns:
        (path_to_key, path_to_csr)
    """
    cuit_clean = "".join(c for c in cuit if c.isdigit())
    if len(cuit_clean) != 11:
        raise ValueError("CUIT debe tener 11 dígitos")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    key_path = output_dir / "arca_private.key"
    csr_path = output_dir / "arca_request.csr"

    # Generate RSA private key (2048 bits, AFIP requirement)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )

    # Subject must include serialNumber=CUIT nnnnnnnnnnn
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Colppy"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"CUIT {cuit_clean}"),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit_clean}"),
    ])

    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(subject)
        .sign(private_key, hashes.SHA256(), default_backend())
    )

    # Write private key (unencrypted for simplicity; use passphrase in prod)
    with open(key_path, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    # Write CSR
    with open(csr_path, "wb") as f:
        f.write(csr.public_bytes(serialization.Encoding.PEM))

    return key_path, csr_path


def main() -> None:
    cuit = os.getenv("ARCA_CUIT", "")
    if not cuit and len(sys.argv) > 1:
        cuit = sys.argv[1]
    if not cuit:
        print("Usage: python generate_csr.py <CUIT> [output_dir]")
        print("   or: ARCA_CUIT=20268448536 python generate_csr.py")
        sys.exit(1)

    output_dir = Path(__file__).resolve().parents[1] / "certs"
    if len(sys.argv) > 2:
        output_dir = Path(sys.argv[2])

    try:
        key_path, csr_path = generate_csr(cuit, output_dir)
        print("Generated:")
        print(f"  Private key: {key_path}")
        print(f"  CSR:         {csr_path}")
        print()
        print("Next steps:")
        print("  1. Log in to WSASS: https://auth.afip.gob.ar/contribuyente_/login.xhtml")
        print("  2. Upload the CSR file (arca_request.csr)")
        print("  3. Download the certificate (.crt or .pem)")
        print("  4. Associate the certificate with 'veconsumerws' in WSASS")
        print("  5. Place cert and key in arca-prototype/certs/ and set ARCA_CERT_PATH, ARCA_KEY_PATH in .env")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
