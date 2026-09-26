# Word report template

Generate (or regenerate) the template from BrandProfile:

```powershell
python -m backend.app.reporting.build_word_template
```

Output file (gitignored):

`Tender_Comparison_Template.docx`

The builder writes docxtpl placeholders, for example:

- `{{ project_id }}`
- `{{ project_name }}`
- `{{ project_location }}`
- `{{ executive_summary }}`
- `{{ recommendation }}`
- `{{ introduction }}`
- `{{ commercial_analysis }}`
- `{{ project_description }}`
- `{{ responses_count }}`
- `{{ tenders_issued_date }}`
- `{{ tender_deadline_date }}`
- `{{ addendums_issued_count }}`

Loop examples:

```jinja2
{% for step in next_steps %}
- {{ step }}
{% endfor %}
```

```jinja2
{% for row in tender_rows %}
{{ row.contractor }} | {{ row.final_adjusted_tender_sum }}
{% endfor %}
```

```jinja2
{% for name in tenderers %}
- {{ name }}
{% endfor %}
```

Tender review matrix (contractors as columns, three fixed rows):

```jinja2
Header row:
Item | {% for name in tender_review_contractors %}{{ name }} | {% endfor %}

Body rows:
{% for r in tender_review_rows %}
{{ r.label }} | {% for v in r.values %}{{ v }} | {% endfor %}
{% endfor %}
```

Colours, company name, registration number, website, font family, and logo
come from `BrandProfile` (`branding.yaml` or `BRAND_*` env). Re-run the
builder after branding changes.
