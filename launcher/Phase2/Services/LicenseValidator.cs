using System;
using System.IO;
using System.Management;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace OfficeAgent.Wpf.Services;

public enum LicenseStatus
{
    Valid,
    FileNotFound,
    ParseError,
    InvalidSignature,
    Expired,
    NotYetValid,
    HardwareMismatch,
    TierMismatch,
}

/// <summary>
/// Validates the license.key file using an embedded RSA public key.
///
/// License file format (license.key):
/// {
///   "schema_version": 1,
///   "org_name": "...",
///   "license_type": "site",        // "site" | "machine"
///   "tier": "standard",            // "standard" | "pro"
///   "valid_from": "2026-04-11",
///   "valid_until": "2027-04-11",
///   "hardware_id": "SITE_LICENSE", // or XXXX-XXXX-XXXX-XXXX fingerprint
///   "features": ["word","excel","powerpoint"],
///   "issued_at": "2026-04-11T00:00:00Z",
///   "signature": "BASE64_RSA_SHA256"
/// }
///
/// Phase 1 note: the embedded public key is a placeholder. In Phase 2,
/// replace EMBEDDED_PUBLIC_KEY_XML with the actual vendor RSA public key.
/// </summary>
internal sealed class LicenseValidator
{
    // RSA public key in XML format (replace with real key before production).
    // Generate with:
    //   var rsa = RSA.Create(2048);
    //   File.WriteAllText("public.xml", rsa.ToXmlString(false));
    private const string EMBEDDED_PUBLIC_KEY_XML = "PLACEHOLDER_RSA_PUBLIC_KEY_XML";

    private readonly string _licenseFilePath;

    public LicenseValidator(string installRoot)
    {
        _licenseFilePath = Path.Combine(installRoot, "license.key");
    }

    public LicenseStatus Validate(string requiredTier)
    {
        // --- Read file ------------------------------------------------------
        if (!File.Exists(_licenseFilePath))
            return LicenseStatus.FileNotFound;

        string json;
        try { json = File.ReadAllText(_licenseFilePath, Encoding.UTF8); }
        catch { return LicenseStatus.ParseError; }

        // --- Parse ----------------------------------------------------------
        JsonDocument doc;
        try { doc = JsonDocument.Parse(json); }
        catch { return LicenseStatus.ParseError; }

        using (doc)
        {
            var root = doc.RootElement;

            if (!TryGetString(root, "signature", out string signature))
                return LicenseStatus.ParseError;

            // --- Signature verification ------------------------------------
            // Phase 1: skip verification if public key is a placeholder.
            bool skipSig = EMBEDDED_PUBLIC_KEY_XML.StartsWith("PLACEHOLDER");

            if (!skipSig)
            {
                // Build the canonical payload (everything except "signature").
                string payload = BuildSignaturePayload(json);
                if (!VerifySignature(payload, signature))
                    return LicenseStatus.InvalidSignature;
            }

            // --- Date validation -------------------------------------------
            if (!TryGetString(root, "valid_from", out string validFrom) ||
                !TryGetString(root, "valid_until", out string validUntil))
                return LicenseStatus.ParseError;

            var today = DateTime.UtcNow.Date;
            if (DateTime.TryParse(validFrom,  out var from) && today < from)
                return LicenseStatus.NotYetValid;
            if (DateTime.TryParse(validUntil, out var until) && today > until)
                return LicenseStatus.Expired;

            // --- Hardware check --------------------------------------------
            if (TryGetString(root, "hardware_id", out string hwId) &&
                hwId != "SITE_LICENSE")
            {
                string currentHw = ComputeHardwareId();
                if (!string.Equals(hwId, currentHw, StringComparison.OrdinalIgnoreCase))
                    return LicenseStatus.HardwareMismatch;
            }

            // --- Tier check ------------------------------------------------
            if (TryGetString(root, "tier", out string licensedTier) &&
                !string.Equals(licensedTier, requiredTier, StringComparison.OrdinalIgnoreCase))
                return LicenseStatus.TierMismatch;
        }

        return LicenseStatus.Valid;
    }

    /// <summary>Returns the hardware fingerprint for the current machine.</summary>
    public string GetHardwareId() => ComputeHardwareId();

    // -----------------------------------------------------------------------
    // Signature helpers
    // -----------------------------------------------------------------------
    private static string BuildSignaturePayload(string json)
    {
        // Remove the "signature" key-value pair before hashing.
        // Simple approach: strip from JSON string.
        // Production builds should use a canonical serialisation.
        var doc = JsonDocument.Parse(json);
        using var ms = new MemoryStream();
        using var writer = new Utf8JsonWriter(ms, new JsonWriterOptions { Indented = false });

        writer.WriteStartObject();
        foreach (var prop in doc.RootElement.EnumerateObject())
        {
            if (prop.Name == "signature") continue;
            prop.WriteTo(writer);
        }
        writer.WriteEndObject();
        writer.Flush();

        return Encoding.UTF8.GetString(ms.ToArray());
    }

    private static bool VerifySignature(string payload, string base64Signature)
    {
        try
        {
            using var rsa = RSA.Create();
            rsa.FromXmlString(EMBEDDED_PUBLIC_KEY_XML);
            byte[] data = Encoding.UTF8.GetBytes(payload);
            byte[] sig  = Convert.FromBase64String(base64Signature);
            return rsa.VerifyData(data, sig, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        }
        catch
        {
            return false;
        }
    }

    // -----------------------------------------------------------------------
    // Hardware fingerprint (WMI-based, three factors)
    // -----------------------------------------------------------------------
    private static string ComputeHardwareId()
    {
        string cpu    = QueryWmi("Win32_Processor",  "ProcessorId") ?? "UNKNOWN_CPU";
        string board  = QueryWmi("Win32_BaseBoard",  "SerialNumber") ?? "UNKNOWN_BOARD";
        string disk   = QueryWmi("Win32_DiskDrive",  "SerialNumber") ?? "UNKNOWN_DISK";

        string combined = $"{cpu}|{board}|{disk}";
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes(combined));

        // Format first 8 bytes as XXXX-XXXX-XXXX-XXXX (4 groups of 4 hex chars).
        return string.Format("{0:X4}-{1:X4}-{2:X4}-{3:X4}",
            BitConverter.ToUInt16(hash, 0),
            BitConverter.ToUInt16(hash, 2),
            BitConverter.ToUInt16(hash, 4),
            BitConverter.ToUInt16(hash, 6));
    }

    private static string? QueryWmi(string className, string propertyName)
    {
        try
        {
            using var searcher = new ManagementObjectSearcher($"SELECT {propertyName} FROM {className}");
            foreach (ManagementObject obj in searcher.Get())
            {
                var val = obj[propertyName]?.ToString()?.Trim();
                if (!string.IsNullOrWhiteSpace(val)) return val;
            }
        }
        catch { /* WMI unavailable */ }
        return null;
    }

    private static bool TryGetString(JsonElement el, string key, out string value)
    {
        if (el.TryGetProperty(key, out var prop) && prop.ValueKind == JsonValueKind.String)
        {
            value = prop.GetString() ?? "";
            return true;
        }
        value = "";
        return false;
    }
}
