## Reporting Brand Assets

Brand identity for PDF/DOCX exports and AI report prompts is driven by
**`BrandProfile`** ([`../branding.py`](../branding.py)):

1. Copy [`branding.example.yaml`](../../../../branding.example.yaml) to repo-root
   `branding.yaml` (gitignored) and customise, **or**
2. Set `BRAND_*` environment variables (`BRAND_COMPANY_NAME`,
   `BRAND_REGISTRATION_NUMBER`, `BRAND_WEBSITE`, `BRAND_LOGO_PATH`,
   `BRAND_FONT_FAMILY`, `BRAND_FONT_BODY_FILE`, `BRAND_FONT_HEADING_FILE`,
   `BRAND_ACCENT_COLOUR`).

### Asset layout

Put logo and font files under:

- `assets/logos/` — referenced by `logo_path` in branding config
- `assets/fonts/` — TTF files named by `font_body_file` / `font_heading_file`

Example:

```yaml
company_name: "Your Company Name"
registration_number: "CN 00000000"
website: "example.com"
logo_path: "backend/app/reporting/assets/logos/company_logo.png"
font_family: "Archivo"
font_body_file: "Archivo_Expanded-Light.ttf"
font_heading_file: "Archivo_Expanded-Bold.ttf"
accent_colour: "#32c3e2"
```

### Notes

- Missing logo files are skipped (reports export without a header logo).
- Relative asset paths for WeasyPrint are resolved using `base_url` set to the
  `reporting` directory when the logo lives under this tree.
- Logo files under `assets/logos/` remain gitignored; keep a local copy or
  point `logo_path` at your private brand asset.
